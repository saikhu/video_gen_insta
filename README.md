# vgi — local, quality-first AI video pipeline for Instagram Reels

Turns a topic into a finished 9:16 Reel with cinematic visuals, narration, animated captions and a
compliance check, entirely on your own hardware. Two content tracks ship today:

Scripts are written by a **local LLM** (Ollama, `qwen3.8:27b` by default) with no API key; Claude is an
optional backend. Each reel is a short **dramatic film**: a cold-open hook, rising stakes, a turn held on a
pause, and a closing line that echoes the hook, cut as **10-16 narration beats with 1-3 shots each** (~20-30
cuts a minute), title cards, per-beat transitions, and the video model's own sound swelling between lines.

| track | what it makes | grounding |
|---|---|---|
| `islamic_battles` | documentary shorts about famous early-Islamic battles | cited fact sheet from a local, open-license corpus; strict depiction rules |
| `memes` | original AI-written jokes as short clips | invented characters only; originality check against past jokes |

Everything runs on a MacBook Pro (M5 Max 48 GB) for authoring and keyframes, and on a Linux
2×RTX 3090 box for motion video through ComfyUI. The research behind the model choices, the
platform policy constraints and the cost/revenue verdict live in `docs/` and the plan file.

## How it works

```
                 PART A · prompt generation (cheap, reviewable)                   PART B · media generation (GPU)
 ┌──────────┐   ┌────────┐   ┌───────────┐   ┌────────────┐  human   ┌─────┐  ┌───────┐  ┌───────┐  ┌──────────┐  ┌────────┐
 │ research │ → │ script │ → │ keyframes │ → │ storyboard │ ──gate──→│ tts │→ │ video │→ │captions│→ │ assemble │→ │ qa     │→ export
 │ cited    │   │ scene  │   │ 3 cands   │   │ preview    │ approve  │     │  │ LTX   │  │ ASS   │  │ ffmpeg   │  │ spec,  │  mp4 +
 │ facts    │   │ plan   │   │ per scene │   │ .html      │          │     │  │ 2.5   │  │karaoke│  │ xfade    │  │ faces, │  cover +
 └──────────┘   └────────┘   └───────────┘   └────────────┘          └─────┘  └───────┘  └───────┘  │ loudnorm │  │ LUFS   │  caption
   local LLM       treatment   Z-Image /       Jinja2                 Kokoro   ComfyUI    engine     └──────────┘  └────────┘
   (Ollama) or     → beats +   FLUX 3 Klein,                                   LTX-2.5,   word
   Claude          shots       one per shot                                    one clip   timings
                                                                               per shot
```

- **One job folder per video** (`outputs/jobs/<id>/`) with a `manifest.json` state machine:
  `created → planned → approved → rendered → qa_passed | qa_failed → exported`.
- **Every stage is cached** by a hash of the inputs that actually determine its output (prompts,
  seeds, model, frame counts, upstream artifacts). Editing a keyframe choice never re-renders clips.
- **The review gate is real.** `render` refuses to run unless the approved plan's hash still matches
  `scene_plan.json`; editing the plan after approval drops the job back to `planned`.
- **Degraded paths are explicit.** No ComfyUI endpoint → Ken Burns over the keyframe. ffmpeg without
  libass → captions skipped and QA fails. Silent audio → loudness pass 2 skipped and QA warns.

## How a reel is structured

| unit | what it is | where it is set |
|---|---|---|
| **beat** | one or two spoken sentences (≤ 22 words) + optional title card, transition in, dramatic pause after | `configs/stages/script.yaml` (`beats_min/max`, `beat_words_max`) |
| **shot** | one camera setup under a beat: keyframe → 2-4 s LTX clip with its own camera move and diegetic sound | `shots_per_beat_max`, `video.min_shot_seconds` |
| **timeline** | beat = pre-roll + narration + post-roll + pause; shots split it; transitions overlap; narration runs continuously over the cut | `core/timeline.py`, `configs/stages/video.yaml` (pacing, `transitions`) |
| **mix** | narration on top; the clips' own sound cleaned (invented music stripped, silent heads skipped, levels matched) and rebuilt into one continuous location track with crossfades that lead each cut; a quiet wind room tone underneath; a fixed gain envelope rides it under the voice and lets it swell in pauses | `configs/stages/assemble.yaml` (`sound:`, `grade`), `src/vgi/media/sound.py` |

The writer works in two passes: a free-text **treatment** (`02_script/treatment.md`, shown in the
storyboard) using the craft rules in `src/vgi/topics/craft.py`, then a structured pass into beats and shots.
A **review-and-repair loop** follows: deterministic validators (depiction, music, shot types, density) plus,
for history, a fact check of every line against the fact sheet; the model gets the specific problems back and
fixes only those (`repair_rounds`, log in `02_script/review.json`).

## Status (2026-11-02)

| capability | state |
|---|---|
| Config layer, job manifest, caching, CLI, dry-run, tests | done |
| Research + script via a **local LLM** (Ollama; citations emulated by numbered sources; JSON-schema output) | verified on the Mac with `qwen2.5:14b`; the box uses `qwen3.8:27b` (`vgi llm pull`) |
| Dramatic structure: treatment → 10-16 beats × 1-3 shots, title cards, transitions, film grade | **verified** on the box: `qwen3.8:27b` → 11 beats / 33 shots → LTX-2.5 on 4×4090 → QA pass |
| Sound design: music stripped from LTX audio, continuous location track, voice-led mix | **verified** by re-mixing the box reel (no dropouts at cuts, −14.1 LUFS); listen and tune `assemble.sound` |
| Claude backend (optional, `backend: claude`) | code done; needs `ANTHROPIC_API_KEY` |
| Keyframes on the Mac (mflux Z-Image Turbo, in-process) | **verified**: 768×1344, ~44 s/image, ~32 GB peak |
| Narration (Kokoro-82M, lexicon IPA, engine word timings) | **verified** |
| Captions (ASS karaoke, honorific → ﷺ merge, safe zones) | **verified** |
| Assembly (xfade, loudness to −14 LUFS with a linear gain + limiter, faststart) and QA (spec, YuNet faces, loudness, audio dropouts) | **verified** |
| Motion video (LTX-2.5 on the Linux box via ComfyUI) | **verified** on a 4×4090 box: full 8-scene reel rendered in parallel (~8.5 min video stage), 1088×1920 25 fps clips with LTX's native audio, QA passed |
| Memes track end to end, ACE-Step music, Fish Drama 3 voice | v1.5 |
| Instagram API publishing (`is_ai_generated=true`, R2 hosting) | v2 |

## Quick start (Mac)

```bash
brew install ffmpeg-full espeak-ng               # libass for captions; espeak for rare words
uv python pin 3.12.15 && uv sync --extra dev --extra tts --extra mac --extra qa
ollama serve & ollama pull qwen3.8:27b            # the local writer (or set llm.local.model to one you have)
curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
uv run vgi doctor
```

```bash
uv run vgi corpus wikipedia "Battle of Badr"      # CC BY-SA text with attribution header → data/corpus/islamic/
uv run vgi new --topic islamic_battles --subject "Battle of Badr"
uv run vgi plan latest                            # Part A → 04_storyboard/preview.html
uv run vgi pick latest 3.2 1                      # beat 3, shot 2 → keyframe candidate 1
uv run vgi tidy latest                            # optional: re-apply honorific/length/pacing fixes after hand edits
uv run vgi approve latest
uv run vgi render latest                          # Part B
uv run vgi qa latest && uv run vgi export latest  # → 09_final/{<job id>.mp4, cover.jpg, caption.txt, metadata.json}
```

`latest` means the newest job. Any unique part of a job id also works (`vgi render 032134`); `uv run vgi jobs`
lists them. Don't type `<job>` literally: bash reads `<` as a file redirect.

`uv run vgi run <job> --dry-run` pushes a placeholder reel through every stage with no models or
API key (the test suite does the same). `uv run vgi jobs`, `vgi logs <job> --stage video` and
`vgi doctor` are the day-to-day inspection commands.

## Linux render farm (ComfyUI, one instance per GPU)

Clone the repo on the disk with ≥ 150 GB free and run one script; everything it installs stays
**inside the repo folder** and is gitignored:

| what | where | ignored |
|---|---|---|
| ComfyUI + venv, per-GPU output/temp | `runtime/comfy/` | yes |
| model files (~97 GB, verified names in `comfy/models.yaml`) | `models/<subfolder>/` | yes |
| job outputs | `outputs/jobs/` | yes |

```bash
git clone git@github.com:saikhu/video_gen_insta.git && cd video_gen_insta
cp .env.example .env            # HF_TOKEN=hf_... (gated LTX-2.5 repo: accept its terms on huggingface.co first)
bash scripts/setup_linux.sh     # --inspect | --skip-models | --no-systemd (then scripts/comfy_tmux.sh)
bash scripts/comfy_smoke.sh     # health + VRAM per endpoint, then `vgi doctor`
```

An *env profile* is a file in `configs/env/` describing one machine; every `vgi` command accepts
`--env <name>` and otherwise auto-detects it (`linux_4x4090` for four GPUs, `linux_2x3090` otherwise;
`VGI_ENV` overrides). Instance N serves GPU N on port 8188+N as the systemd unit `comfy@N`
(`journalctl -u comfy@0 -f`). The API-format workflow templates in `comfy/workflows/` are generated from the official ComfyUI
templates with `{{placeholders}}` (see `comfy/specs/` and `scripts/ui_to_api.py`), so no manual export is needed. From the Mac, `ssh -N -L 8188:127.0.0.1:8188 <box>` and
`comfy.endpoints` in `configs/env/mac_m5max.yaml` let the laptop drive the farm.

## Parameter files

Precedence: `configs/global.yaml` < `configs/stages/<stage>.yaml` < `configs/topics/<topic>.yaml` <
`configs/env/<env>.yaml` < `--set key.path=value`. Hardware always wins; topic and env files reach
into stage settings through a `stages:` block. A job freezes the content config (everything except
env) at `vgi new`, so the same job folder renders on either machine.

| file | controls |
|---|---|
| `global.yaml` | reel spec (1080×1920, 25 fps, 45-75 s, −14 LUFS / −1 dBTP), caption safe zones, seed base |
| `env/mac_m5max.yaml`, `env/linux_2x3090.yaml`, `env/linux_4x4090.yaml` | one **env profile** per machine: backends per stage, ComfyUI endpoints, RAM/VRAM, electricity rate. Selected with `--env <name>`, else `VGI_ENV`, else auto-detected (macOS → `mac_m5max`; Linux → by GPU count) |
| `topics/islamic_battles.yaml` | corpus dir, subjects, depiction rule + shot whitelist, honorifics, `music_policy: native_only`, hashtags |
| `topics/memes.yaml` | formats, banned characters/topics, originality threshold, ACE-Step prompt |
| `stages/research.yaml` … `stages/publish.yaml` | one file per stage: models, steps, resolutions, candidates, xfade/tail, caption style, QA thresholds |
| `styles/*.yaml`, `voices/*.yaml` | prompt prefix/suffix and references; narrator voice per engine |
| `pronunciation/lexicon.yaml` | Arabic names → IPA (Kokoro inline `[Badr](/bædr/)`) and respellings |
| `llm.yaml` | the writer: local Ollama host/model/context (default `qwen3.8:27b`, alt `gemma4:31b`) and the optional Claude model |
| `pricing.yaml` | Claude token prices, ElevenLabs, KRW→USD for the per-reel cost in `metadata.json` |

## Repository layout

```
src/vgi/
  cli.py                 typer commands (new, plan, preview, pick, approve, render, qa, export, run, jobs, logs, doctor, corpus, models)
  config/                YAML loader + pydantic schemas + .env secrets
  core/                  job manifest, stage base + caching, runner, hashing/seeds, JSONL logging, cost
  llm/                   Claude client (citations pass, parse() pass, refusal fallbacks) and the offline stub
  topics/                islamic_battles.py (corpus retrieval, prompts, validators), memes.py (idea pool, originality)
  stages/                one module per stage + the Jinja2 storyboard template
  backends/              comfy_client.py, image/{mflux,comfy}, video/{ken_burns,comfy_video}, tts/kokoro
  media/                 ffmpeg.py (segments, xfade, loudness, Ken Burns), sound.py (clip sound → location track, mix), ass.py (karaoke), images.py
comfy/                   API-format workflow templates (to export), models.yaml, custom_nodes.txt, systemd unit
scripts/                 setup_linux.sh (idempotent install), comfy_instance.sh, comfy_tmux.sh, comfy_smoke.sh, ui_to_api.py
configs/                 all parameters (see above)
runtime/ models/ outputs/   created by the scripts/pipeline, gitignored
data/corpus/islamic/     open-license source texts (gitignored except README)
docs/                    SETUP_MAC.md · SETUP_LINUX.md · POLICY.md · LEARNING_PATH.md
tests/                   config precedence, state machine, caching, caption math, full dry run
```

## Models (all commercial-OK at this scale)

| role | model | why |
|---|---|---|
| keyframes (Mac) | Z-Image Turbo via mflux (Apache) | runs in 48 GB, 8 steps, film-look realism; ignores negative prompts (exclusions are phrased positively) |
| keyframes (Linux) | Z-Image Turbo int8 (Apache) by default; FLUX 3 Image Klein optional | FLUX has the top open image Elo, but its HF repo card calls the Kommunity license non-commercial while other sources say free under $5M — verify before monetizing |
| video | LTX-2.5 int8_convrot (free < $10M) | synchronized native audio, portrait, first/last-frame chaining; Wan 2.2 (Apache) as fallback |
| narration | Kokoro-82M (Apache) → Fish Drama 3 later | word timestamps for free; IPA overrides; Fish needs ~39 GB VRAM |
| music | none (Islamic) / ACE-Step 1.5 (memes) | no instruments policy; LTX's own sound, with its invented score stripped, carries the ambience |
| LLM | local `qwen3.8:27b` via Ollama (Apache 2.0, 17.7 GB, fits one 4090) | free; GPU hand-off frees ComfyUI first; Claude Opus 5.5 optional (≈ $0.25/script) |

Excluded on license grounds: MiniMax H3 and HunyuanVideo 1.5 (territory restrictions incl. Korea),
FLUX.1/2 dev (non-commercial), F5-TTS / Higgs / VibeVoice (research-only), MMAudio (NC).

## Cost

Local generation ≈ **$0.30-0.40 per reel** (≈ $0.20 Claude + a few cents of electricity) versus
$3-48 per reel for cloud video APIs. Measured on the 4×4090 box: ~2 min for 24 keyframes, ~8.5 min for
eight LTX-2.5 clips rendered four at a time (one 8 s clip ≈ 4.5 min on one card), ~2 min for narration,
captions and assembly → **~13 min per reel**, ≈ 0.4 kWh. On the Mac alone: ~18 min of keyframes plus a
Ken Burns reel (no motion model). Realistic revenue for a new account is near zero for 3-6 months; see the plan
file for the full review.

## Policy baked in

No faces of the Prophet ﷺ, other prophets, his household or Companions (prompt rules, shot
whitelist, human gate, YuNet face check). Honorifics spoken in full and rendered as ﷺ / (RA) in
captions. No instrumental music on the Islamic track. Original characters only for memes. Every
export carries the AI disclosure in the caption and `ai_generated: true` in `metadata.json`. See
`docs/POLICY.md`.

## Troubleshooting

| symptom | fix |
|---|---|
| `No such filter: 'ass'` | Homebrew's plain `ffmpeg` has no libass → `brew install ffmpeg-full` (auto-detected; or `VGI_FFMPEG=…`) |
| `cannot import name '_IntegralLike'` | Pillow 13 on Python 3.12 → already pinned `pillow<13`; rerun `uv sync` |
| mflux writes `scene_01_c0_1.png` | mflux never overwrites; the backend pre-deletes targets and settles suffixed files |
| `-inf` in loudnorm | audio is silent (stub TTS) → pass 2 is skipped automatically, QA warns |
| music or drones under the narration | LTX invents a score; `assemble.sound.demusic` strips sustained tones (`demusic_keep` lower = stronger). Negative prompts do nothing: the distilled model samples at CFG 1 |
| sound jumps or holes at cuts | see `09_final/assemble.json` → `shot_sound` (per-shot level, music removed, unused shots); raise `sound.xfade_s` or `level_match` |
| Wikipedia 403 | set a descriptive `VGI_HTTP_UA` (Wikimedia's user-agent policy) |
| `plan changed after approval` | `vgi approve <job>` again (the hash protects you from rendering an unreviewed edit) |

## Roadmap

1. **Phase 3** Linux render farm: ComfyUI × 2, LTX-2.5 workflows, benchmark seconds/clip.
2. Real Claude runs with the corpus; Fish Drama 3 behind the GPU lease; Claude-vision candidate pick.
3. Memes track end to end with ACE-Step beds; Korean-language track (Qwen3-TTS / ElevenLabs).
4. v2 publishing: Cloudflare R2 + Instagram API with Instagram Login, Trial Reels, 1-2 posts/day cron.

## Third topic in story development

[Where the Burrows Lead](docs/stories/where-the-burrows-lead/README.md) is a proposed 24-minute
meerkat fantasy adventure, released as sixteen connected 1–2 minute chapters. The development package
contains the character bible, world rules, full treatment and chapter continuity plan. It is not yet
a registered topic or a rendered movie; dialogue and character-consistency support are planned in its
production handoff.
