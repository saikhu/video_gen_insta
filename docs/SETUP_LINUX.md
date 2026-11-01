# Linux render farm runbook (2×RTX 3090 or 4×RTX 4090)

You run these on the Linux box yourself. Everything is idempotent: re-run a step if it fails.
Estimated time: 20 min of commands + 1-3 h of model downloads depending on bandwidth.

## 0. Prerequisites (one-time, needs sudo)

- Ubuntu 22.04/24.04 (other distros work; swap `apt` for your package manager).
- NVIDIA driver **≥ 550** with CUDA 12 support. Check: `nvidia-smi` shows both 3090s.
  If missing: `sudo ubuntu-drivers install` (or the `.run` installer) and reboot.
- ~150 GB free disk on the filesystem where you clone the repo (models ≈ 97 GB, ComfyUI + venvs ≈ 15 GB, outputs grow).
- A Hugging Face token (https://huggingface.co/settings/tokens) **and gated-repo access**: open
  https://huggingface.co/Lightricks/LTX-2.5 while logged in, accept the terms / request access, and wait for the
  approval email (minutes to a day). Without it every LTX download returns 401. FLUX 3 Klein
  (https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy) is optional and also gated; its repo card
  calls the license non-commercial, so leave it out until you have read the license text.

## 1. Clone the repo and run the setup script

```bash
git clone git@github.com:saikhu/video_gen_insta.git     # on the filesystem with >= 150 GB free; everything stays inside this folder
cd video_gen_insta
bash scripts/setup_linux.sh --inspect          # just reports GPUs, driver, RAM, disk, ffmpeg/libass
```

If the inspection looks right:

```bash
cp .env.example .env && nano .env              # HF_TOKEN=hf_... (and ANTHROPIC_API_KEY for real scripts)
bash scripts/setup_linux.sh                    # full install: ComfyUI + PyTorch cu12 + SageAttention + nodes + models + services
```

What the script does, in order (each step is skipped when already done):

| step | what | where |
|---|---|---|
| 1 | `apt install git ffmpeg espeak-ng build-essential tmux`, installs `uv` | system |
| 2 | clones ComfyUI, creates `.venv`, installs PyTorch **cu128** wheels, ComfyUI requirements, `sageattention==1.0.6` + triton | `runtime/comfy/ComfyUI` |
| 3 | clones ComfyUI-GGUF, KJNodes, Frame-Interpolation; writes `extra_model_paths.yaml` pointing at the shared models dir | `runtime/comfy/ComfyUI/custom_nodes`, `models/` |
| 4 | `uv sync` for vgi (`dev`, `tts`, `qa` extras), downloads the YuNet face model | repo root (`.venv/`, `models/`) |
| 5 | `vgi models pull` from `comfy/models.yaml` (~97 GB: LTX-2.5 39.7, Wan 2.2 37.8, Z-Image 14.6, SeedVR2 4; resumable; add `--include-optional` for FLUX) | `models/<subfolder>` |
| 6 | installs `comfy@.service` and starts one instance per GPU: `comfy@N` on port 8188+N (`scripts/comfy_instance.sh`) | systemd |

Flags: `--no-systemd` (then `bash scripts/comfy_tmux.sh` starts both instances in tmux), `--skip-models`.
Overrides (only if you want ComfyUI or the models outside the repo): `COMFY_ROOT=<dir> MODELS_DIR=<dir> bash scripts/setup_linux.sh`.

**Layout:** everything the script installs stays inside the repo and is gitignored: `runtime/comfy/ComfyUI`
(+ its venv), `models/<subfolder>`, `outputs/jobs`. So clone the repo on the disk with space and run the
script with no overrides.

**What "env" means.** An *env profile* is one YAML file under `configs/env/` that describes a machine: which
backend each stage uses, the ComfyUI endpoints, RAM/VRAM and the electricity rate. The ones that ship:

| profile (`configs/env/<name>.yaml`) | machine |
|---|---|
| `mac_m5max` | MacBook Pro M5 Max: keyframes via mflux, Kokoro, video through a tunnel or Ken Burns |
| `linux_2x3090` | Linux with two RTX 3090: two ComfyUI endpoints (8188, 8189) |
| `linux_4x4090` | Linux with four RTX 4090: four endpoints (8188-8191) |

Every `vgi` command takes `--env <name>`; when you omit it, the name is taken from the `VGI_ENV` environment
variable, else detected (macOS → `mac_m5max`; Linux → `linux_4x4090` if `nvidia-smi` lists four or more
GPUs, otherwise `linux_2x3090`). The setup script prints the profile it chose on its first lines. A job
remembers the env it was created with, and the env is the only part of the configuration that is **not**
frozen into the job, so the same job folder can be rendered under another profile. To add a machine, copy
one of these files, rename it, and edit the `comfy.endpoints` and `stages:` overrides.

## 2. Verify

```bash
bash scripts/comfy_smoke.sh                    # health + VRAM of each endpoint, then `vgi doctor` (auto-detected env)
journalctl -u comfy@0 -f                       # if an instance is not up
```

`vgi doctor` must show every endpoint **ok** with free VRAM ≈ 23 GB, `libass (captions) ok` and
`dual ComfyUI instances ok`.

## 3. Export the workflow templates (manual, once)

The pipeline drives ComfyUI with API-format JSON that contains `{{placeholders}}`. ComfyUI's UI is
bound to localhost only, so open a tunnel from your Mac:

```bash
ssh -N -L 8188:127.0.0.1:8188 <linux-host>      # then browse http://127.0.0.1:8188
```

For each template below: **Workflow → Browse Templates**, load it, set the controlled inputs to the
placeholder strings, then **Workflow → Export (API)** and save into `comfy/workflows/` in the repo.

| save as | start from ComfyUI template | placeholders to put in node inputs |
|---|---|---|
| `video_ltx25_i2v.json` | `video_ltx2_5_i2v` | LoadImage.image = `{{image}}`; positive prompt = `{{prompt}}`; negative = `{{negative}}`; KSampler/seed = `{{seed}}`; length/frames = `{{frames}}`; width/height = `{{width}}` `{{height}}`; steps = `{{steps}}`; fps = `{{fps}}`; SaveVideo.filename_prefix = `{{prefix}}` |
| `video_ltx25_flf2v.json` | `video_ltx2_5_flf2v` | same + second LoadImage.image = `{{last_image}}` |
| `image_z_image_turbo.json` | Z-Image Turbo template (Browse Templates → Image) with the int8 diffusion model, `qwen_3_4b` text encoder, `ae` VAE | prompt `{{prompt}}`, width/height `{{width}}` `{{height}}`, seed `{{seed}}`, steps `{{steps}}`, SaveImage.filename_prefix = `{{prefix}}` (Turbo has no negative/guidance; the pipeline ignores them) |
| `image_flux3_klein.json` (optional) | FLUX 3 Klein template (needs ComfyUI ≥ 0.41) | same plus negative `{{negative}}` and guidance `{{guidance}}` |
| `video_wan22_i2v.json` (fallback) | `video_wan2_2_14B_i2v`, replacing both "Load Diffusion Model" nodes with "Unet Loader (GGUF)" (category `bootleg`) pointing at the Q8_0 files in `models/unet` | same as i2v |

Rules: a numeric input whose whole value is the placeholder becomes a number automatically; leave the
model-loader nodes pointing at the files from `comfy/models.yaml`; keep the LTX text-encoder unload
step the tutorial uses (24 GB). Commit the JSON files (`git add comfy/workflows/*.json`).

## 4. First real clip and benchmark

```bash
uv run vgi new --topic islamic_battles --subject "Battle of Badr"      # --env <profile> only if auto-detection is wrong
uv run vgi plan <job>            # Claude if ANTHROPIC_API_KEY is set, else stub; keyframes via FLUX 3 Klein on GPU
uv run vgi approve <job>
uv run vgi run <job> --from video --until video --scene 1     # one LTX-2.5 clip; watch `vgi logs <job> --stage video`
```

Record the measured seconds per clip as a comment under `stages.video` in the env profile you used
(`configs/env/linux_4x4090.yaml` on the 4090 box),
then render the whole reel: `uv run vgi render <job> && uv run vgi qa <job> && uv run vgi export <job>`.

## 5. Driving the box from the Mac (optional)

```bash
ssh -N -L 8188:127.0.0.1:8188 -L 8189:127.0.0.1:8189 <linux-host>
```

and set `comfy.endpoints: ["http://127.0.0.1:8188", "http://127.0.0.1:8189"]` in `configs/env/mac_m5max.yaml`.
Keyframes made on the Mac are uploaded through `/upload/image` before I2V. Job folders are not synced;
each machine renders the jobs in its own `outputs/`.

## 6. Day-2 operations

- Update ComfyUI: `cd runtime/comfy/ComfyUI && git pull && uv pip install --python .venv/bin/python -r requirements.txt && sudo systemctl restart comfy@0 comfy@1`.
- Free VRAM between jobs: `curl -X POST http://127.0.0.1:8188/free -d '{"unload_models":true,"free_memory":true}'`.
- Output/temp folders: `runtime/comfy/output/<gpu>` and `runtime/comfy/temp/<gpu>`; the pipeline copies results
  into the job folder, so these can be cleaned (`find runtime/comfy/output -mtime +7 -delete`).
- Power: two 3090s under load ≈ 850 W. `nvidia-smi -pl 280` per GPU trims ~20% power for ~5% speed if the room gets hot.

## Troubleshooting

| symptom | fix |
|---|---|
| `torch.cuda.is_available() == False` | driver too old or CPU wheel installed → `nvidia-smi`, then rerun step 2 (the script pins the cu128 index) |
| `sageattention` import error at launch | remove `--use-sage-attention` from the unit/tmux command; speed drops ~25% |
| OOM on the LTX second stage (1088×1920) | set `stages.video.upscale: 1` and use the SeedVR2 fallback, or lower `base_width/height` |
| download 401/403 (LTX-2.5, FLUX) | request/accept access on the Hugging Face repo page, wait for approval, set `HF_TOKEN` in `.env`, re-run `uv run vgi models pull --only ltx25` |
| black frames from SeedVR2 | disable FlashAttention in the SeedVR2 workflow (known on RTX 30 with INT8 checkpoints) |
| `--use-sage-attention` silently ignored | Triton needs `python3-dev`; check `journalctl -u comfy@0` for a sageattention import error |
| file name mismatch in `comfy/models.yaml` | open the repo page on Hugging Face, fix the `file:` path, re-run `uv run vgi models pull --only <name>` |
| two instances OOM in system RAM | `comfy.dual_instance: false` and only enable `comfy@0` |
