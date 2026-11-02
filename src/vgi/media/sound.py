"""Sound design: the clips' own sound becomes one continuous location track under the narration.

Why this exists: LTX-2.5 invents a new soundtrack for every clip. With 2-3 s shots that is a new soundscape at
every cut. Clips often start with 0.1-1 s of silence (audible holes at the cut), and most carry a sustained
music drone. The distilled model samples at CFG 1, so a negative prompt such as "music" has no effect.

Steps (numpy, deterministic):
  per shot  decode, high-pass, strip sustained tones (harmonic/percussive separation keeps wind, hooves and
            impacts), find the span that actually has sound, bring it toward one common level
  layout    each shot's sound sits on its picture time and is mirrored past its edges, so a crossfade never
            lands in a hole; neighbours join with equal-power crossfades that lead the picture cut (J-cut)
  glue      a quiet synthetic room tone (wind) under everything, so the reel never drops to digital silence
  mix       narration on its timeline; location sound and any music bed ride under it on a fixed gain
            envelope (automation, not a compressor, so nothing pumps between words)
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .ffmpeg import FFmpegError, ffmpeg_bin

MIX_VERSION = "sound-v2"     # part of the assemble cache key: bump when the mixing algorithm changes


# ---------- io ----------
def decode_audio(path: Path, sr: int, channels: int = 2) -> np.ndarray:
    """Media file -> float32 array (channels, n) at `sr`. Raises if the file has no audio stream."""
    proc = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", str(channels),
                           "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=False)
    if proc.returncode != 0:
        raise FFmpegError(f"decode {path.name} failed: {proc.stderr.decode(errors='replace')[-400:]}")
    x = np.frombuffer(proc.stdout, np.float32)
    return x[: len(x) // channels * channels].reshape(-1, channels).T.copy()


def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    import soundfile as sf

    sf.write(str(path), np.ascontiguousarray(x.T), sr, subtype="FLOAT")


# ---------- levels ----------
def db(v: float) -> float:
    return float(20 * np.log10(max(float(v), 1e-12)))


def from_db(d: float) -> float:
    return float(10 ** (d / 20))


def window_rms(x: np.ndarray, sr: int, win: float = 0.05) -> np.ndarray:
    """RMS per `win`-second window over all channels."""
    hop = max(1, int(sr * win))
    n = x.shape[-1] // hop
    if n == 0:
        return np.zeros(0)
    fr = x[..., : n * hop].reshape(*x.shape[:-1], n, hop)
    axes = (0, 2) if x.ndim == 2 else (1,)
    return np.sqrt(np.mean(fr.astype(np.float64) ** 2, axis=axes))


def active_rms_db(x: np.ndarray, sr: int, gate_db: float = -50.0) -> float:
    """Level of the parts that have sound (speech level, not the pauses)."""
    r = window_rms(x, sr)
    if r.size == 0:
        return -120.0
    loud = r[20 * np.log10(r + 1e-12) > gate_db]
    return db(np.sqrt(np.mean(loud ** 2))) if loud.size else -120.0


# ---------- filters ----------
def highpass(x: np.ndarray, sr: int, hz: float, order: int = 2) -> np.ndarray:
    if hz <= 0:
        return x
    from scipy.signal import butter, sosfilt

    return sosfilt(butter(order, hz, "highpass", fs=sr, output="sos"), x, axis=-1).astype(np.float32)


def peaking(x: np.ndarray, sr: int, f0: float, gain_db: float, q: float = 0.9) -> np.ndarray:
    """RBJ peaking EQ (a dip when gain_db < 0)."""
    if not gain_db:
        return x
    from scipy.signal import lfilter

    a_ = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    b = np.array([1 + alpha * a_, -2 * np.cos(w0), 1 - alpha * a_])
    a = np.array([1 + alpha / a_, -2 * np.cos(w0), 1 - alpha / a_])
    return lfilter(b / a[0], a / a[0], x, axis=-1).astype(np.float32)


def demusic(x: np.ndarray, sr: int, keep: float = 0.08, t_kern: float = 0.35, f_kern_hz: float = 400.0,
            n_fft: int = 2048) -> np.ndarray:
    """Harmonic/percussive separation with soft masks (Fitzgerald 2010). Sustained tones, which show as horizontal
    lines in a spectrogram (drones, chords, held notes), are removed; noise-like and transient sound (wind, hooves,
    crowd texture, impacts) stays. `keep` is the fraction of the tonal part that survives (1 = filter off)."""
    if keep >= 1.0 or x.shape[-1] < n_fft:
        return x
    from scipy.ndimage import median_filter
    from scipy.signal import istft, stft

    hop = n_fft // 4
    _, _, spec = stft(x, sr, nperseg=n_fft, noverlap=n_fft - hop)
    mag = np.abs(spec).mean(axis=0) if spec.ndim == 3 else np.abs(spec)
    tk = max(3, int(t_kern * sr / hop) | 1)
    fk = max(3, int(f_kern_hz * n_fft / sr) | 1)
    harm = median_filter(mag, size=(1, tk), mode="reflect") ** 2
    perc = median_filter(mag, size=(fk, 1), mode="reflect") ** 2
    mask = keep + (1.0 - keep) * perc / (harm + perc + 1e-12)
    _, y = istft(spec * mask, sr, nperseg=n_fft, noverlap=n_fft - hop)
    y = y[..., : x.shape[-1]]
    if y.shape[-1] < x.shape[-1]:
        y = np.pad(y, [(0, 0)] * (y.ndim - 1) + [(0, x.shape[-1] - y.shape[-1])])
    return y.astype(np.float32)


def content_span(x: np.ndarray, sr: int, below_db: float = 12.0, floor_db: float = -60.0,
                 win: float = 0.02) -> tuple[int, int] | None:
    """Sample span between the first and last window that carries the clip's body of sound (louder than the clip
    level minus `below_db`, and above `floor_db`). LTX often leaves a silent head that ramps up, and sometimes a
    silent tail; mirroring must not reflect around those ramps, or the crossfade dips."""
    r = window_rms(x, sr, win)
    if r.size == 0:
        return None
    lv = 20 * np.log10(r + 1e-12)
    ref = active_rms_db(x, sr, floor_db)
    on = np.nonzero(lv > max(floor_db, ref - below_db))[0]
    if on.size == 0:
        return None
    hop = int(sr * win)
    return int(on[0] * hop), int(min(x.shape[-1], (on[-1] + 1) * hop))


def _mirror(idx: np.ndarray, a: int, b: int) -> np.ndarray:
    """Map sample indices onto [a, b) by mirroring at the edges (a triangle wave)."""
    span = max(1, b - a)
    u = np.mod(idx - a, 2 * span)
    return np.clip(a + np.where(u < span, u, 2 * span - 1 - u), a, b - 1)


def _ramp(n: int, rising: bool) -> np.ndarray:
    """Equal-power ramp (quarter sine) of n samples."""
    if n <= 0:
        return np.ones(0, np.float32)
    w = np.sin(0.5 * np.pi * (np.arange(n) + 0.5) / n).astype(np.float32)
    return w if rising else w[::-1]


def room_tone(n: int, sr: int, seed: int, low: float = 70.0, high: float = 900.0) -> np.ndarray:
    """Soft wind: band-limited brown noise with slow random gusts, decorrelated stereo, unit RMS."""
    from scipy.signal import butter, lfilter, sosfilt

    rng = np.random.default_rng(seed)
    w = rng.standard_normal((2, n)).astype(np.float32)
    brown = lfilter([1.0], [1.0, -0.995], w, axis=-1)
    brown = sosfilt(butter(2, [low, high], "bandpass", fs=sr, output="sos"), brown, axis=-1)
    ctrl_rate = 100
    m = n // (sr // ctrl_rate) + 4
    c = sosfilt(butter(2, 0.15, "lowpass", fs=ctrl_rate, output="sos"), rng.standard_normal((2, m)), axis=-1)
    c = c / (c.std(axis=-1, keepdims=True) + 1e-9)
    t_ctrl = np.arange(m) / ctrl_rate
    t = np.arange(n) / sr
    gust = np.stack([np.interp(t, t_ctrl, 0.72 + 0.28 * np.tanh(ch)) for ch in c])
    y = brown * gust
    y = np.stack([0.8 * y[0] + 0.2 * y[1], 0.2 * y[0] + 0.8 * y[1]])
    return (y / (np.sqrt(np.mean(y ** 2)) + 1e-12)).astype(np.float32)


def envelope(n: int, sr: int, intervals: list[tuple[float, float]], gap_db: float, under_db: float,
             attack: float, release: float) -> np.ndarray:
    """Gain curve: `gap_db` in the gaps, riding down to `under_db` over each narration interval. The ramp down ends
    as the voice starts; the ramp up starts as it ends (raised-cosine ramps, computed on a 1 kHz control grid)."""
    rate = 1000
    m = int(np.ceil(n / sr * rate)) + 2
    t = np.arange(m) / rate
    d = np.zeros(m)
    for a, b in intervals:
        x = np.clip((t - (a - attack)) / max(attack, 1e-3), 0, 1)
        y = np.clip(((b + release) - t) / max(release, 1e-3), 0, 1)
        d = np.maximum(d, 0.5 - 0.5 * np.cos(np.pi * np.minimum(x, y)))
    g = 10 ** ((gap_db + (under_db - gap_db) * d) / 20)
    return np.interp(np.arange(n) / sr, t, g).astype(np.float32)


# ---------- location track ----------
@dataclass
class ShotSound:
    shot_id: str
    start: float                       # picture start on the reel timeline
    overlap: float = 0.0               # picture transition into the next shot
    audio: np.ndarray | None = None    # (2, n), index 0 = the clip's first frame
    info: dict[str, Any] = field(default_factory=dict)


def prepare_shot(s: ShotSound, sr: int, cfg: Any, ref_db: float) -> None:
    """Clean one shot's sound in place: high-pass, de-music, find its span, level-match toward `ref_db`."""
    if s.audio is None or s.audio.shape[-1] == 0:
        s.audio, s.info = None, {"used": False, "why": "no audio"}
        return
    x = highpass(s.audio, sr, cfg.highpass_hz)
    before = active_rms_db(x, sr, -70)
    if cfg.demusic:
        x = demusic(x, sr, keep=cfg.demusic_keep)
    after = active_rms_db(x, sr, -70)
    span = content_span(x, sr)
    info: dict[str, Any] = {"level_db": round(after, 1), "music_removed_db": round(before - after, 1)}
    if span is None or (span[1] - span[0]) / sr < cfg.min_content_s or after < -65:
        s.audio, s.info = None, {**info, "used": False, "why": "too little sound"}
        return
    lv = active_rms_db(x[:, span[0]:span[1]], sr, -70)
    gain = float(np.clip((ref_db - lv) * cfg.level_match, -30.0, cfg.max_boost_db))
    if lv + gain < ref_db - cfg.max_shortfall_db:      # near-silent clip: a hole even after boosting
        s.audio, s.info = None, {**info, "used": False, "why": f"too quiet ({lv:.0f} dB)"}
        return
    s.audio = x * from_db(gain)
    s.info = {**info, "used": True, "gain_db": round(gain, 1), "head_s": round(span[0] / sr, 2),
              "span": (span[0], span[1])}


def layout(shots: list[ShotSound], total: float, sr: int, cfg: Any) -> np.ndarray:
    """Place each usable shot's sound on the reel timeline with equal-power crossfades that lead the picture cut by
    `jcut_s`. A shot that has no usable sound is covered by its neighbours."""
    n = round(total * sr)
    out = np.zeros((2, n), np.float32)
    use = [s for s in shots if s.audio is not None and s.info.get("used")]
    for k, s in enumerate(use):
        prev_c = s.start - cfg.jcut_s if k else None
        next_c = use[k + 1].start - cfg.jcut_s if k + 1 < len(use) else None
        w_in = max(cfg.xfade_s, use[k - 1].overlap) if k else cfg.start_fade_s
        w_out = max(cfg.xfade_s, s.overlap) if next_c is not None else cfg.end_fade_s
        if prev_c is not None and next_c is not None:     # keep both fades inside the shot's own stretch
            room = max(0.05, next_c - prev_c)
            w_in, w_out = min(w_in, 0.9 * room), min(w_out, 0.9 * room)
        t0 = max(0.0, prev_c - w_in / 2) if prev_c is not None else 0.0
        t1 = min(total, next_c + w_out / 2) if next_c is not None else total
        i0, i1 = round(t0 * sr), round(t1 * sr)
        if i1 <= i0:
            continue
        a, b = s.info["span"]
        src = _mirror(np.arange(i0, i1) - round(s.start * sr), a, b)
        g = np.ones(i1 - i0, np.float32)
        nin, nout = min(int(w_in * sr), i1 - i0), min(int(w_out * sr), i1 - i0)
        g[:nin] *= _ramp(nin, True)
        g[i1 - i0 - nout:] *= _ramp(nout, False)
        out[:, i0:i1] += s.audio[:, src] * g
    return out


def mix_reel(narration: list[tuple[np.ndarray, float]], location: np.ndarray | None, bed: np.ndarray | None,
             total: float, sr: int, cfg: Any, seed: int, bed_gap_db: float = -10.0, bed_duck_db: float = -10.0
             ) -> tuple[np.ndarray, dict[str, Any]]:
    """Final stereo mix (float32, peak <= 0.9; the finalize pass sets the loudness)."""
    n = round(total * sr)
    out = np.zeros((2, n), np.float32)
    intervals: list[tuple[float, float]] = []
    voice = [highpass(x, sr, 70) for x, _ in narration]
    vlev = active_rms_db(np.concatenate(voice, axis=-1), sr) if voice else -120.0
    vgain = from_db(cfg.voice_db - vlev) if vlev > -100 else 1.0
    for x, (_, start) in zip(voice, narration):
        i0 = round(start * sr)
        if i0 >= n:
            continue
        seg = x[:, : n - i0] * vgain
        out[:, i0:i0 + seg.shape[-1]] += seg
        intervals.append((start, start + x.shape[-1] / sr))
    report: dict[str, Any] = {"voice_level_in_db": round(vlev, 1), "intervals": len(intervals)}
    if location is not None:       # shots were levelled to voice_db; the envelope is relative to the voice
        loc = peaking(location[:, :n], sr, 2800, cfg.presence_dip_db, 0.8)
        env = envelope(n, sr, intervals, cfg.diegetic_gap_db, cfg.diegetic_db, cfg.duck_attack_s, cfg.duck_release_s)
        out[:, : loc.shape[-1]] += loc * env[: loc.shape[-1]]
    if cfg.room_tone != "none":
        out += room_tone(n, sr, seed) * from_db(cfg.voice_db + cfg.room_tone_db)
    if bed is not None and bed.size:
        reps = int(np.ceil(n / bed.shape[-1]))
        b = np.tile(bed, (1, reps))[:, :n]
        b = b * from_db(cfg.voice_db - active_rms_db(b, sr))
        b = peaking(b, sr, 2800, cfg.presence_dip_db, 0.8)
        out += b * envelope(n, sr, intervals, bed_gap_db, bed_gap_db + bed_duck_db, cfg.duck_attack_s,
                            cfg.duck_release_s)
    fade = min(n, int(cfg.end_fade_s * sr))
    out[:, n - fade:] *= _ramp(fade, False)
    peak = float(np.abs(out).max()) if n else 0.0
    if peak > 0.9:
        out *= 0.9 / peak
    report["peak_scaled_db"] = round(db(0.9 / peak), 1) if peak > 0.9 else 0.0
    return out, report


def silent_gaps(x: np.ndarray, sr: int, floor_db: float = -60.0, min_s: float = 0.08,
                skip_head: float = 0.3, skip_tail: float = 1.6) -> list[float]:
    """Start times of stretches at least `min_s` long that are quieter than `floor_db` (audible dropouts)."""
    win = 0.02
    r = window_rms(x, sr, win)
    quiet = 20 * np.log10(r + 1e-12) < floor_db
    need = max(1, round(min_s / win))
    gaps: list[float] = []
    run = 0
    for i, q in enumerate(quiet):
        run = run + 1 if q else 0
        t = (i - need + 1) * win
        if run == need and skip_head <= t <= len(r) * win - skip_tail:
            gaps.append(round(t, 2))
    return gaps
