"""Thin, explicit ffmpeg/ffprobe wrappers. Every function builds one command and runs it."""
from __future__ import annotations

import functools
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class FFmpegError(RuntimeError):
    pass


_CANDIDATES = ["/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin", "/opt/homebrew/bin", "/usr/local/bin",
               "/usr/bin"]


@functools.lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    """Pick an ffmpeg that has libass (the `ass` filter). VGI_FFMPEG overrides. Falls back to PATH's ffmpeg."""
    override = os.environ.get("VGI_FFMPEG")
    if override:
        return override
    cands = [shutil.which("ffmpeg")] + [str(Path(d) / "ffmpeg") for d in _CANDIDATES]
    seen: list[str] = []
    for c in cands:
        if c and Path(c).exists() and c not in seen:
            seen.append(c)
    for c in seen:
        try:
            out = subprocess.run([c, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
        except Exception:  # noqa: BLE001
            continue
        if re.search(r"\bass\b", out):
            return c
    return seen[0] if seen else "ffmpeg"


def ffprobe_bin() -> str:
    override = os.environ.get("VGI_FFPROBE")
    if override:
        return override
    sibling = Path(ffmpeg_bin()).with_name("ffprobe")
    return str(sibling) if sibling.exists() else (shutil.which("ffprobe") or "ffprobe")


def has_libass() -> bool:
    out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return re.search(r"\bass\b", out) is not None


def run(cmd: list[str], cwd: Path | None = None) -> str:
    if cmd and cmd[0] == "ffmpeg":
        cmd = [ffmpeg_bin(), *cmd[1:]]
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"{' '.join(cmd[:3])} failed ({proc.returncode}):\n{tail}")
    return proc.stderr


def probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip())
    return json.loads(proc.stdout)


def duration(path: Path) -> float:
    info = probe(path)
    return float(info["format"].get("duration", 0.0))


def has_audio(path: Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def stream_info(path: Path) -> dict[str, Any]:
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {
        "width": int(v.get("width", 0)), "height": int(v.get("height", 0)), "fps": fps,
        "vcodec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "acodec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate", 0) or 0),
        "channels": int(a.get("channels", 0) or 0),
        "duration": float(info["format"].get("duration", 0)),
        "bitrate_mbps": float(info["format"].get("bit_rate", 0) or 0) / 1e6,
        "size_bytes": int(info["format"].get("size", 0) or 0),
    }


def moov_before_mdat(path: Path) -> bool:
    """True when the MP4 is 'faststart' (moov atom precedes mdat)."""
    with Path(path).open("rb") as f:
        data = f.read(1 << 20)
    im, id_ = data.find(b"moov"), data.find(b"mdat")
    return im != -1 and (id_ == -1 or im < id_)


def silence_wav(out: Path, seconds: float, sample_rate: int = 24000) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
         "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(out)])


def tone_wav(out: Path, seconds: float, sample_rate: int = 24000, freq: int = 220, gain_db: float = -28.0) -> None:
    """Quiet placeholder 'voice' for stub TTS so loudness normalization has real signal to measure."""
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={sample_rate}",
         "-t", f"{seconds:.3f}", "-af", f"volume={gain_db}dB,tremolo=f=2.5:d=0.6", "-c:a", "pcm_s16le", str(out)])


def frames_for(seconds: float, fps: int, grid: int) -> int:
    """Frame count rounded UP to grid*k+1 (LTX requires 8k+1)."""
    n = max(1, math.ceil(seconds * fps))
    k = math.ceil((n - 1) / grid)
    return grid * k + 1


def ken_burns(image: Path, out: Path, seconds: float, fps: int, width: int, height: int,
              zoom_start: float = 1.0, zoom_end: float = 1.12, pre_scale: float = 1.6, direction: int = 0) -> None:
    """Pan/zoom over a still. direction 0..3 chooses the pan vector; zoom is linear over the clip."""
    frames = max(2, int(round(seconds * fps)))
    pw, ph = int(width * pre_scale) // 2 * 2, int(height * pre_scale) // 2 * 2
    dz = (zoom_end - zoom_start) / frames
    pans = [
        ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("(iw-iw/zoom)*on/{n}".format(n=frames), "ih/2-(ih/zoom/2)"),
        ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{n}".format(n=frames)),
        ("(iw-iw/zoom)*(1-on/{n})".format(n=frames), "(ih-ih/zoom)*on/{n}".format(n=frames)),
    ]
    x, y = pans[direction % 4]
    vf = (f"scale={pw}:{ph}:force_original_aspect_ratio=increase:flags=lanczos,crop={pw}:{ph},"
          f"zoompan=z='min({zoom_start}+{dz:.6f}*on,{zoom_end})':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
          f"format=yuv420p")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(image), "-t", f"{seconds:.3f}",
         "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out)])


def make_segment(video_in: Path, narration: Path | None, out: Path, seconds: float, lead_s: float,
                 width: int, height: int, fps: int, sample_rate: int, diegetic_gain_db: float = -10.0,
                 bed: Path | None = None, bed_gain_db: float = -18.0, duck_db: float = -12.0,
                 use_clip_audio: bool = True) -> None:
    """Normalize one scene to reel geometry, pad/trim to `seconds`, mix narration (offset by lead) + diegetic."""
    inputs = ["-i", str(video_in)]
    graph = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
             f"fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration={seconds:.3f},trim=duration={seconds:.3f},"
             f"setpts=PTS-STARTPTS[v]"]
    audio_labels: list[str] = []
    idx = 1
    if narration is not None:
        inputs += ["-i", str(narration)]
        ms = int(round(lead_s * 1000))
        graph.append(f"[{idx}:a]aresample={sample_rate},aformat=channel_layouts=stereo,adelay={ms}|{ms},apad[n]")
        audio_labels.append("[n]")
        idx += 1
    if use_clip_audio and has_audio(video_in):
        graph.append(f"[0:a]aresample={sample_rate},aformat=channel_layouts=stereo,volume={diegetic_gain_db}dB,apad[d]")
        audio_labels.append("[d]")
    if bed is not None:
        inputs += ["-stream_loop", "-1", "-i", str(bed)]
        graph.append(f"[{idx}:a]aresample={sample_rate},aformat=channel_layouts=stereo,volume={bed_gain_db}dB,apad[b0]")
        if narration is not None:
            graph.append("[b0][n]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400:makeup=1[b]")
            # sidechaincompress consumes [n]; re-create it for the mix
            graph.append(f"[{1}:a]aresample={sample_rate},aformat=channel_layouts=stereo,adelay={ms}|{ms},apad[n2]")
            audio_labels = [lbl for lbl in audio_labels if lbl != "[n]"] + ["[n2]", "[b]"]
        else:
            audio_labels.append("[b0]")
        idx += 1
    if not audio_labels:
        graph.append(f"anullsrc=r={sample_rate}:cl=stereo[a]")
    elif len(audio_labels) == 1:
        graph.append(f"{audio_labels[0]}anull[a]")
    else:
        graph.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:normalize=0:dropout_transition=0,"
                     f"alimiter=limit=0.95:level=false[a]")
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
           "-t", f"{seconds:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "16",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), "-ac", "2", str(out)]
    run(cmd)


def concat_xfade(segments: list[Path], durations: list[float], out: Path, xfade: float, transition: str,
                 fps: int, sample_rate: int) -> float:
    """Chain xfade/acrossfade over segments. Returns resulting duration."""
    if len(segments) == 1:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(segments[0]), "-c", "copy", str(out)])
        return durations[0]
    inputs: list[str] = []
    for s in segments:
        inputs += ["-i", str(s)]
    graph: list[str] = []
    vprev, aprev, offset = "[0:v]", "[0:a]", 0.0
    for i in range(1, len(segments)):
        offset += durations[i - 1] - xfade
        vout = f"[v{i}]" if i < len(segments) - 1 else "[v]"
        aout = f"[a{i}]" if i < len(segments) - 1 else "[a]"
        graph.append(f"{vprev}[{i}:v]xfade=transition={transition}:duration={xfade:.3f}:offset={offset:.3f}{vout}")
        graph.append(f"{aprev}[{i}:a]acrossfade=d={xfade:.3f}:c1=tri:c2=tri{aout}")
        vprev, aprev = vout, aout
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
         "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), str(out)])
    return sum(durations) - xfade * (len(segments) - 1)


def loudnorm_measure(path: Path, i: float, tp: float, lra: float) -> dict[str, Any]:
    stderr = run(["ffmpeg", "-v", "info", "-i", str(path), "-af",
                  f"loudnorm=I={i}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not m:
        raise FFmpegError("loudnorm measurement not found in ffmpeg output")
    data = json.loads(m.group(0))
    for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        try:
            v = float(data.get(k, "nan"))
        except (TypeError, ValueError):
            v = float("nan")
        if not math.isfinite(v):
            data["unmeasurable"] = True  # silent audio → pass-2 cannot use these numbers
    return data


def finalize(src: Path, out: Path, ass_rel: str | None, measured: dict[str, Any] | None, i: float, tp: float,
             lra: float, crf: int, preset: str, pix_fmt: str, fps: int, sample_rate: int, audio_kbps: int,
             font_dirs: list[str], cwd: Path, grade: list[str] | None = None) -> None:
    """Grade + burn captions + apply loudnorm (pass 2) + faststart. `ass_rel` is relative to cwd (avoids escaping)."""
    vf = list(grade or [])
    if ass_rel and not has_libass():
        ass_rel = None  # caller logs the warning; output is produced without burned-in captions
    if ass_rel:
        fonts = next((d for d in font_dirs if Path(d).exists()), None)
        vf.append(f"ass=filename={ass_rel}" + (f":fontsdir={fonts}" if fonts else ""))
    vf.append(f"format={pix_fmt}")
    if measured and not measured.get("unmeasurable"):
        af = (f"loudnorm=I={i}:TP={tp}:LRA={lra}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
              f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
              f":offset={measured['target_offset']}:linear=true:print_format=summary")
    else:
        af = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", ",".join(vf), "-af", af, "-r", str(fps),
         "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", pix_fmt,
         "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ar", str(sample_rate), "-ac", "2",
         "-movflags", "+faststart", str(out)], cwd=cwd)


def extract_frame(video: Path, t: float, out: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)])


def render_ass_on_blank(ass_rel: str, out: Path, width: int, height: int, t: float, font_dirs: list[str], cwd: Path) -> None:
    """Render the subtitle track over a black frame at time t (used by the safe-zone test)."""
    fonts = next((d for d in font_dirs if Path(d).exists()), None)
    flt = f"ass=filename={ass_rel}" + (f":fontsdir={fonts}" if fonts else "")
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r=25", "-ss", f"{t:.3f}",
         "-vf", flt, "-frames:v", "1", str(out)], cwd=cwd)


# ---------------------------------------------------------------- shot-based assembly (beats + shots)
def grade_filters(cfg: dict[str, Any] | None) -> list[str]:
    """Film look applied to the whole reel before captions: contrast/saturation, vignette, grain."""
    if not cfg or not cfg.get("enabled", True):
        return []
    f = [f"eq=contrast={cfg.get('contrast', 1.0)}:saturation={cfg.get('saturation', 1.0)}:brightness={cfg.get('brightness', 0.0)}"]
    if cfg.get("vignette"):
        f.append(f"vignette=angle={cfg.get('vignette_angle', 'PI/5')}")
    if cfg.get("grain", 0):
        f.append(f"noise=alls={int(cfg['grain'])}:allf=t")
    return f


PAD_FRAMES = 3


def make_shot_segment(clip: Path, out: Path, length: float, width: int, height: int, fps: int, sample_rate: int,
                      use_clip_audio: bool = True) -> None:
    """Normalize one shot to reel geometry. Audio is exactly `length` seconds (sample-accurate, keeps sync); video
    gets PAD_FRAMES extra frames because frame rounding would otherwise leave the next xfade window a fraction of a
    frame short, which makes ffmpeg's xfade silently stop emitting video. The extra frames fall inside the next
    transition (or are trimmed at the end)."""
    vlen = length + PAD_FRAMES / fps
    graph = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1,"
             f"tpad=stop_mode=clone:stop_duration={vlen:.3f},trim=duration={vlen:.3f},setpts=PTS-STARTPTS[v]"]
    if use_clip_audio and has_audio(clip):
        graph.append(f"[0:a]aresample={sample_rate},aformat=channel_layouts=stereo,apad,atrim=duration={length:.3f},"
                     f"asetpts=PTS-STARTPTS[a]")
    else:
        graph.append(f"anullsrc=r={sample_rate}:cl=stereo,atrim=duration={length:.3f}[a]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
         "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), "-ac", "2", str(out)])


def xfade_chain(segments: list[Path], owns: list[float], boundaries: list[tuple[str, float]], out: Path, fps: int,
                sample_rate: int) -> float:
    """segments[i] is owns[i] + boundaries[i].duration long; boundary i joins segment i and i+1 with xfade/acrossfade.
    Offsets are the cumulative `own` sums, so the result is exactly sum(owns) long."""
    if len(segments) == 1:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(segments[0]), "-c", "copy", str(out)])
        return owns[0]
    inputs: list[str] = []
    for sgm in segments:
        inputs += ["-i", str(sgm)]
    graph: list[str] = []
    vprev, aprev, offset = "[0:v]", "[0:a]", 0.0
    for i in range(1, len(segments)):
        name, d = boundaries[i - 1]
        d = max(0.04, d)
        offset += owns[i - 1]
        last = i == len(segments) - 1
        vout, aout = ("[v]", "[a]") if last else (f"[v{i}]", f"[a{i}]")
        graph.append(f"{vprev}[{i}:v]xfade=transition={name}:duration={d:.3f}:offset={offset:.3f}{vout}")
        graph.append(f"{aprev}[{i}:a]acrossfade=d={d:.3f}:c1=tri:c2=tri{aout}")
        vprev, aprev = vout, aout
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
         "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), str(out)])
    return round(sum(owns), 3)


def mix_narration(video: Path, narration: list[tuple[Path, float]], total: float, out: Path, sample_rate: int,
                  diegetic_gain_db: float = -6.0, duck_threshold: float = 0.03, duck_ratio: float = 6.0,
                  duck_release_ms: int = 450, bed: Path | None = None, bed_gain_db: float = -18.0) -> None:
    """Lay one continuous narration track (each line at its absolute start) over the cut; the clips' own sound
    is side-chain ducked under the voice, so it swells in the gaps and dramatic pauses."""
    inputs = ["-i", str(video)]
    graph: list[str] = []
    labels = []
    for i, (wav, start) in enumerate(narration, start=1):
        ms = int(round(start * 1000))
        inputs += ["-i", str(wav)]
        graph.append(f"[{i}:a]aresample={sample_rate},aformat=channel_layouts=stereo,adelay={ms}|{ms}[n{i}]")
        labels.append(f"[n{i}]")
    if labels:
        graph.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0,apad,"
                     f"atrim=duration={total:.3f},asplit=2[narr][key]")
    else:
        graph.append(f"anullsrc=r={sample_rate}:cl=stereo,atrim=duration={total:.3f},asplit=2[narr][key]")
    graph.append(f"[0:a]volume={diegetic_gain_db}dB[dg]")
    graph.append("[key]asplit=2[k1][k2]")
    graph.append(f"[dg][k1]sidechaincompress=threshold={duck_threshold}:ratio={duck_ratio}:attack=15:"
                 f"release={duck_release_ms}[dgd]")
    mix = ["[narr]", "[dgd]"]
    if bed is not None:
        inputs += ["-stream_loop", "-1", "-i", str(bed)]
        bi = len(narration) + 1
        graph.append(f"[{bi}:a]aresample={sample_rate},aformat=channel_layouts=stereo,volume={bed_gain_db}dB,"
                     f"atrim=duration={total:.3f}[bed]")
        graph.append(f"[bed][k2]sidechaincompress=threshold={duck_threshold}:ratio={duck_ratio}:attack=20:release=600[bedd]")
        mix.append("[bedd]")
    else:
        graph.append("[k2]anullsink")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:dropout_transition=0,alimiter=limit=0.95:level=false,"
                 f"atrim=duration={total:.3f}[a]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), "-t", f"{total:.3f}", str(out)])


def video_duration(path: Path) -> float:
    info = probe(path)
    v = next((st for st in info["streams"] if st.get("codec_type") == "video"), {})
    return float(v.get("duration") or info["format"].get("duration") or 0.0)
