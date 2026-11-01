# Mac setup (M5 Max 48 GB)

1. `brew install ffmpeg-full` — the plain `ffmpeg` formula has no libass, so captions cannot be burned in.
   `vgi doctor` shows which binary is used (override with `VGI_FFMPEG=/path/to/ffmpeg`).
2. `uv sync --extra dev --extra tts` — Kokoro needs `espeak-ng` only for out-of-dictionary words: `brew install espeak-ng`.
3. Keyframes on the Mac: `uv sync --extra mac` (mflux). Verified 2026-11-02: `mflux-generate-z-image-turbo` at
   768×1344, 8 steps, `-q 8` peaks at ~32 GB unified memory; the first run downloads the model (~6.5 min incl. download).
   `uv python pin 3.12.15` and `pillow<13` are required: Pillow 13 imports a stdlib symbol CPython 3.12 lacks.
   `stages.keyframes.model` picks the mflux entry point (`z_image_turbo` verified; `flux3_klein` unverified).
4. Render on the Linux box from the Mac: `ssh -N -L 8188:127.0.0.1:8188 -L 8189:127.0.0.1:8189 <linux-host>` then
   set `comfy.endpoints` in `configs/env/mac_m5max.yaml`. Keyframes are uploaded through `/upload/image`.
5. Face QA: download `face_detection_yunet_2023mar.onnx` from opencv_zoo into `models/` and `uv sync --extra qa`.
