#!/usr/bin/env bash
# One-shot, idempotent setup of the vgi render farm on a Linux box with NVIDIA GPUs.
# Run as your normal user (sudo only for apt/systemd). Re-running is safe; finished steps are skipped.
#
#   git clone git@github.com:saikhu/video_gen_insta.git ~/video_gen_insta
#   cd ~/video_gen_insta && bash scripts/setup_linux.sh            # everything
#   bash scripts/setup_linux.sh --inspect                          # only report GPUs/driver/RAM/disk
#   bash scripts/setup_linux.sh --no-systemd                       # skip services (use scripts/comfy_tmux.sh)
#   bash scripts/setup_linux.sh --skip-models                      # skip the ~60 GB download
#
# Env overrides: COMFY_ROOT (default /opt/comfy), MODELS_DIR (default $COMFY_ROOT/models), VGI_ENV (env profile
#   used for `vgi models pull`, default linux_2x3090), HF_TOKEN
set -euo pipefail

COMFY_ROOT="${COMFY_ROOT:-/opt/comfy}"
MODELS_DIR="${MODELS_DIR:-$COMFY_ROOT/models}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSPECT_ONLY=0; USE_SYSTEMD=1; SKIP_MODELS=0
for a in "$@"; do case "$a" in
  --inspect) INSPECT_ONLY=1;; --no-systemd) USE_SYSTEMD=0;; --skip-models) SKIP_MODELS=1;;
  *) echo "unknown flag $a"; exit 2;; esac; done

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '   \033[31m✘ %s\033[0m\n' "$*"; exit 1; }

# ---------------------------------------------------------------- 0. inspect
say "Inspecting the machine"
command -v nvidia-smi >/dev/null || die "nvidia-smi not found: install the NVIDIA driver (>= 550) first"
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader | sed 's/^/   /'
GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
RAM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
DISK_GB=$(df -BG --output=avail "$(dirname "$COMFY_ROOT")" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)
MODELS_DISK_GB=$(df -BG --output=avail "$(dirname "$MODELS_DIR")" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)
ok "GPUs: $GPU_COUNT · RAM: ${RAM_GB} GB · free disk under $(dirname "$COMFY_ROOT"): ${DISK_GB} GB"
[ "$RAM_GB" -ge $((32 * GPU_COUNT)) ] && ok "RAM ${RAM_GB} GB: one ComfyUI instance per GPU fits" || warn "RAM < 64 GB: run ONE video instance (set comfy.dual_instance: false in configs/env/linux_2x3090.yaml)"
ok "free disk under $(dirname "$MODELS_DIR") (models): ${MODELS_DISK_GB} GB"
[ "$MODELS_DISK_GB" -ge 120 ] || warn "need ~120 GB free for models: set MODELS_DIR=/path/with/space"
command -v python3 >/dev/null && ok "python3: $(python3 --version)"
command -v ffmpeg >/dev/null && { ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' ass ' && ok "ffmpeg with libass" || warn "ffmpeg lacks libass (captions): apt install ffmpeg usually includes it; otherwise build with --enable-libass"; } || warn "ffmpeg missing: sudo apt install -y ffmpeg"
[ "$INSPECT_ONLY" = 1 ] && { say "Inspect-only run finished"; exit 0; }

# ---------------------------------------------------------------- 1. system packages
say "System packages"
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq git ffmpeg espeak-ng build-essential python3-dev tmux curl >/dev/null
  ok "apt packages present"
else
  warn "no apt-get: install git ffmpeg espeak-ng build-essential tmux yourself"
fi
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv $(uv --version)"

# ---------------------------------------------------------------- 2. ComfyUI
say "ComfyUI under $COMFY_ROOT"
sudo mkdir -p "$COMFY_ROOT" && sudo chown "$USER" "$COMFY_ROOT"
mkdir -p "$MODELS_DIR"/{diffusion_models,unet,text_encoders,vae,loras,upscale_models,latent_upscale_models,checkpoints}
for i in $(seq 0 $((GPU_COUNT - 1))); do mkdir -p "$COMFY_ROOT/output/$i" "$COMFY_ROOT/temp/$i"; done
if [ ! -d "$COMFY_ROOT/ComfyUI/.git" ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_ROOT/ComfyUI"
fi
cd "$COMFY_ROOT/ComfyUI"
git pull -q --ff-only || true
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv
fi
# PyTorch with CUDA 12.x wheels (3090 = sm_86). Pin the index so uv never picks a CPU wheel.
.venv/bin/python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null \
  || uv pip install --python .venv/bin/python torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python -r requirements.txt -q
# SageAttention 1.x: pure-Triton kernels, works on Ampere (SageAttention 2/3 need Ada/Blackwell builds).
uv pip install --python .venv/bin/python "sageattention==1.0.6" triton -q || warn "sageattention install failed; drop --use-sage-attention from the service unit"
.venv/bin/python -c "import torch; print('   torch', torch.__version__, 'cuda', torch.version.cuda, 'gpus', torch.cuda.device_count())"
ok "ComfyUI $(git rev-parse --short HEAD) with venv"

# ---------------------------------------------------------------- 3. custom nodes + model paths
say "Custom nodes and shared model paths"
cd "$COMFY_ROOT/ComfyUI/custom_nodes"
clone_node() { [ -d "$2" ] || git clone -q --depth 1 "$1" "$2"; [ -f "$2/requirements.txt" ] && uv pip install --python "$COMFY_ROOT/ComfyUI/.venv/bin/python" -r "$2/requirements.txt" -q || true; ok "$2"; }
clone_node https://github.com/city96/ComfyUI-GGUF.git ComfyUI-GGUF
clone_node https://github.com/kijai/ComfyUI-KJNodes.git ComfyUI-KJNodes
clone_node https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git ComfyUI-Frame-Interpolation
sed "s|base_path: /opt/comfy/models|base_path: $MODELS_DIR|" "$REPO_DIR/comfy/extra_model_paths.yaml" > "$COMFY_ROOT/ComfyUI/extra_model_paths.yaml"
ok "extra_model_paths.yaml → $MODELS_DIR"

# ---------------------------------------------------------------- 4. vgi itself
say "vgi (pipeline) at $REPO_DIR"
cd "$REPO_DIR"
uv python pin 3.12 >/dev/null 2>&1 || true
uv sync --extra dev --extra tts --extra qa -q
uv pip install --python .venv/bin/python huggingface_hub -q
[ -f .env ] || cp .env.example .env
mkdir -p models
[ -f models/face_detection_yunet_2023mar.onnx ] || curl -sSL -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
ok "vgi venv ready (uv run vgi --help)"

# ---------------------------------------------------------------- 5. models
if [ "$SKIP_MODELS" = 0 ]; then
  say "Model files → $MODELS_DIR (this is the long step; re-run resumes)"
  [ -n "${HF_TOKEN:-}" ] || grep -q '^HF_TOKEN=.\+' .env || warn "HF_TOKEN not set: gated repos (FLUX 3 Klein) will fail; add it to .env"
  set -a; [ -f .env ] && . ./.env; set +a
  MODELS_DIR="$MODELS_DIR" uv run vgi models pull --env "${VGI_ENV:-linux_2x3090}"
else
  warn "skipping model download (--skip-models)"
fi

# ---------------------------------------------------------------- 6. services
if [ "$USE_SYSTEMD" = 1 ]; then
  say "systemd services comfy@0 and comfy@1"
  sed -e "s|/opt/comfy|$COMFY_ROOT|g" -e "s|User=comfy|User=$USER|" "$REPO_DIR/comfy/systemd/comfy@.service" | sudo tee /etc/systemd/system/comfy@.service >/dev/null
  sudo systemctl daemon-reload
  for i in $(seq 0 $((GPU_COUNT - 1))); do sudo systemctl enable --now "comfy@$i"; done
  sleep 8
  for i in $(seq 0 $((GPU_COUNT - 1))); do
    curl -sf "http://127.0.0.1:818$i/system_stats" >/dev/null && ok "comfy@$i listening on 818$i" || warn "comfy@$i not up yet: journalctl -u comfy@$i -f"
  done
else
  warn "systemd skipped: start instances with  bash scripts/comfy_tmux.sh"
fi

say "Done. Next: uv run vgi doctor --env ${VGI_ENV:-linux_2x3090} ; then export the workflow templates (docs/SETUP_LINUX.md step 3)"
