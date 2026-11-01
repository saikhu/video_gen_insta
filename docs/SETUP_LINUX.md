# Linux render farm (2×RTX 3090, 128 GB RAM)

1. NVIDIA driver ≥ 550, CUDA 12.x. Create `/opt/comfy` owned by a `comfy` user.
2. `pipx install comfy-cli && cd /opt/comfy && comfy --workspace ComfyUI install` (PyTorch cu12x).
   Install SageAttention 1.x (`pip install sageattention`) — Ampere-compatible, ~27% faster.
3. `comfy node install` each entry of `comfy/custom_nodes.txt`.
4. Copy `comfy/extra_model_paths.yaml` to `/opt/comfy/ComfyUI/` and run `vgi models pull --env linux_2x3090`
   (needs `pip install huggingface_hub`, and `HF_TOKEN` for gated repos). Re-check file names in `comfy/models.yaml`
   against the Hugging Face repos first.
5. Copy `comfy/systemd/comfy@.service` to `/etc/systemd/system/` and `systemctl enable --now comfy@0 comfy@1`.
   Both instances share one install and models dir; outputs go to `/opt/comfy/output/<gpu>`.
6. Open ComfyUI once per workflow, load the templates `video_ltx2_5_i2v`, `video_ltx2_5_flf2v` and an image workflow,
   put `{{placeholders}}` in the controlled inputs (see `comfy/workflows/README.md`), export in API format into
   `comfy/workflows/`.
7. `uv sync --extra dev --extra tts --extra qa` for the pipeline itself; run jobs here with
   `VGI_ENV=linux_2x3090` (default on Linux). `vgi doctor` must show both endpoints healthy.
8. Benchmark one clip (`vgi run <job> --from video --until video --scene 1`) and record seconds/clip in the env file.
