from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.stage import RunContext, Stage, StageResult
from ..media.ffmpeg import loudnorm_measure, moov_before_mdat, stream_info


def face_check(video: Path, model: Path, sample_fps: float, threshold: float, width: int, height: int) -> dict[str, Any]:
    """OpenCV YuNet on CPU. Returns {'checked': bool, 'violations': [...]}. Skips if cv2/model missing."""
    try:
        import cv2  # type: ignore
    except ImportError:
        return {"checked": False, "reason": "opencv not installed (uv sync --extra qa)"}
    if not model.exists():
        return {"checked": False, "reason": f"face model missing: {model}"}
    det = cv2.FaceDetectorYN.create(str(model), "", (width, height), 0.8, 0.3, 500)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, int(round(fps / sample_fps)))
    i, violations = 0, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            h, w = frame.shape[:2]
            det.setInputSize((w, h))
            _, faces = det.detect(frame)
            for f in (faces if faces is not None else []):
                if f[3] / h > threshold:
                    violations.append({"t": round(i / fps, 2), "bbox_h_ratio": round(float(f[3] / h), 3)})
        i += 1
    cap.release()
    return {"checked": True, "violations": violations}


class QaStage(Stage):
    name = "qa"
    requires = ("assemble",)

    def run(self, ctx: RunContext) -> StageResult:
        qc, reel = ctx.stage_cfg("qa"), ctx.cfg.global_.reel
        final = ctx.job.dir("assemble") / "final.mp4"
        fails, warns, checks = [], [], {}
        info = stream_info(final)
        checks["stream"] = info
        if qc.spec_check:
            if info["vcodec"] != "h264":
                fails.append(f"video codec {info['vcodec']} != h264")
            if (info["width"], info["height"]) != (reel.width, reel.height):
                fails.append(f"resolution {info['width']}x{info['height']} != {reel.width}x{reel.height}")
            if not (23 <= info["fps"] <= 60):
                fails.append(f"fps {info['fps']:.2f} outside 23-60")
            if info["acodec"] != "aac" or info["sample_rate"] > 48000:
                fails.append(f"audio {info['acodec']} @ {info['sample_rate']} not AAC <= 48 kHz")
            if info["bitrate_mbps"] > reel.video_bitrate_max_mbps:
                fails.append(f"bitrate {info['bitrate_mbps']:.1f} Mbps > {reel.video_bitrate_max_mbps}")
            if info["size_bytes"] > 300 * 1024 * 1024:
                fails.append("file larger than 300 MB")
            if not moov_before_mdat(final):
                fails.append("moov atom is not before mdat (no faststart)")
            if not (reel.min_seconds <= info["duration"] <= reel.max_seconds):
                warns.append(f"duration {info['duration']:.1f}s outside {reel.min_seconds}-{reel.max_seconds}s")
            if info["pix_fmt"] != "yuv420p":
                warns.append(f"pix_fmt {info['pix_fmt']} (Instagram expects 4:2:0)")
        try:
            m = loudnorm_measure(final, reel.loudness_lufs, reel.true_peak_dbtp, 11)
            if m.get("unmeasurable"):
                raise ValueError("audio is silent (loudness unmeasurable)")
            li, tp = float(m["input_i"]), float(m["input_tp"])
            checks["loudness"] = {"integrated_lufs": li, "true_peak_dbtp": tp}
            if abs(li - reel.loudness_lufs) > qc.loudness_tolerance_lu:
                warns.append(f"integrated loudness {li:.1f} LUFS vs target {reel.loudness_lufs}")
            if tp > reel.true_peak_dbtp + 0.5:
                warns.append(f"true peak {tp:.1f} dBTP above {reel.true_peak_dbtp}")
        except Exception as e:  # noqa: BLE001
            warns.append(f"loudness measurement failed: {e}")
        if qc.face_check:
            res = face_check(final, ctx.root / qc.face_model, qc.face_sample_fps, qc.face_threshold, reel.width, reel.height)
            checks["faces"] = res
            if not res.get("checked"):
                warns.append(f"face check skipped: {res.get('reason')}")
            elif res["violations"]:
                fails.append(f"{len(res['violations'])} frames with a prominent face (topic forbids): first at t={res['violations'][0]['t']}s")
        if qc.pronunciation_check:
            warns.append("pronunciation check not implemented in v1 (warn-only)")
        if any("captions NOT burned" in n for n in ctx.job.record("assemble").notes):
            fails.append("captions were not burned in (ffmpeg without libass)")
        verdict = "PASS" if not fails else "FAIL"
        lines = [f"# QA report — {ctx.job.id}", "", f"**Verdict: {verdict}**", ""]
        lines += ["## Hard failures"] + ([f"- {f}" for f in fails] or ["- none"]) + [""]
        lines += ["## Warnings"] + ([f"- {w}" for w in warns] or ["- none"]) + [""]
        lines += ["## Stream", "```", json.dumps(info, indent=1), "```"]
        out_dir = ctx.job.dir("qa")
        (out_dir / "qa_report.md").write_text("\n".join(lines), encoding="utf-8")
        (out_dir / "qa_report.json").write_text(json.dumps({"verdict": verdict, "fails": fails, "warns": warns, "checks": checks},
                                                           indent=2, default=str), encoding="utf-8")
        ctx.job.set_state("qa_passed" if not fails else "qa_failed")
        log = ctx.log.for_stage("qa")
        (log.info if not fails else log.error)(f"{verdict}: {len(fails)} failures, {len(warns)} warnings")
        return StageResult(artifacts=["09_final/qa_report.md", "09_final/qa_report.json"], notes=fails + warns)
