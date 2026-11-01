# vgi — local, quality-first AI video pipeline for Instagram Reels

Turns a topic into a finished 9:16 Reel with cinematic visuals, narration, animated captions and a
compliance check, entirely on your own hardware. Two content tracks ship today:

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
   Claude          Claude      Z-Image /       Jinja2                 Kokoro   ComfyUI    engine     └──────────┘  └────────┘
   citations       parse()     FLUX 3 Klein                                    (Ken Burns  word
                                                                               fallback)   timings
```

- **One job folder per video** (`outputs/jobs/<id>/`) with a `manifest.json` state machine:
  `created → planned → approved → rendered → qa_passed | qa_failed → exported`.
- **Every stage is cached** by a hash of the inputs that actually determine its output (prompts,
  seeds, model, frame counts, upstream artifacts). Editing a keyframe choice never re-renders clips.
- **The review gate is real.** `render` refuses to run unless the approved plan's hash still matches
  `scene_plan.json`; editing the plan after approval drops the job back to `planned`.
- **Degraded paths are explicit.** No ComfyUI endpoint → Ken Burns over the keyframe. ffmpeg without
  libass → captions skipped and QA fails. Silent audio → loudness pass 2 skipped and QA warns.

## Status (2026-11-02)

| capability | state |
|---|---|
| Config layer, job manifest, caching, CLI, dry-run, tests | done |
| Research + script via Claude (citations → structured ScenePlan) | code done; needs `ANTHROPIC_API_KEY` (stub LLM otherwise) |
| Keyframes on the Mac (mflux Z-Image Turbo, in-process) | **verified**: 768×1344, ~44 s/image, ~32 GB peak |
| Narration (Kokoro-82M, lexicon IPA, engine word timings) | **verified** |
| Captions (ASS karaoke, honorific → ﷺ merge, safe zones) | **verified** |
| Assembly (xfade, two-pass loudnorm −14 LUFS, faststart) and QA (spec, YuNet faces, loudness) | **verified** |
| Motion video (LTX-2.5 on the Linux box via ComfyUI) | client, verified model manifest, `scripts/setup_linux.sh` runbook written; **run it on the box** (`docs/SETUP_LINUX.md`) |
| Memes track end to end, ACE-Step music, Fish Drama 3 voice | v1.5 |
| Instagram API publishing (`is_ai_generated=true`, R2 hosting) | v2 |

## Quick start (Mac)

```bash
brew install ffmpeg-full espeak-ng               # libass for captions; espeak for rare words
uv python pin 3.12.15 && uv sync --extra dev --extra tts --extra mac --extra qa
cp .env.example .env                              # add ANTHROPIC_API_KEY for real research/scripts
curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
uv run vgi doctor
```

```bash
uv run vgi corpus wikipedia "Battle of Badr"      # CC BY-SA text with attribution header → data/corpus/islamic/
uv run vgi new --topic islamic_battles --subject "Battle of Badr"
uv run vgi plan <job>                             # Part A → 04_storyboard/preview.html
uv run vgi pick <job> 2 1                         # choose keyframe candidate 1 for scene 2
uv run vgi approve <job>
uv run vgi render <job>                           # Part B
uv run vgi qa <job> && uv run vgi export <job>    # → 09_final/{<job>.mp4, cover.jpg, caption.txt, metadata.json}
```

`uv run vgi run <job> --dry-run` pushes a placeholder reel through every stage with no models or
API key (the test suite does the same). `uv run vgi jobs`, `vgi logs <job> --stage video` and
`vgi doctor --env linux_2x3090` are the day-to-day inspection commands.

## Parameter files

Precedence: `configs/global.yaml` < `configs/stages/<stage>.yaml` < `configs/topics/<topic>.yaml` <
`configs/env/<env>.yaml` < `--set key.path=value`. Hardware always wins; topic and env files reach
into stage settings through a `stages:` block. A job freezes the content config (everything except
env) at `vgi new`, so the same job folder renders on either machine.

| file | controls |
|---|---|
| `global.yaml` | reel spec (1080×1920, 25 fps, 45-75 s, −14 LUFS / −1 dBTP), caption safe zones, seed base |
| `env/mac_m5max.yaml`, `env/linux_2x3090.yaml` | backends per stage, ComfyUI endpoints, RAM/VRAM, electricity rate |
| `topics/islamic_battles.yaml` | corpus dir, subjects, depiction rule + shot whitelist, honorifics, `music_policy: native_only`, hashtags |
| `topics/memes.yaml` | formats, banned characters/topics, originality threshold, ACE-Step prompt |
| `stages/research.yaml` … `stages/publish.yaml` | one file per stage: models, steps, resolutions, candidates, xfade/tail, caption style, QA thresholds |
| `styles/*.yaml`, `voices/*.yaml` | prompt prefix/suffix and references; narrator voice per engine |
| `pronunciation/lexicon.yaml` | Arabic names → IPA (Kokoro inline `[Badr](/bædr/)`) and respellings |
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
  media/                 ffmpeg.py (segments, xfade, loudnorm, Ken Burns), ass.py (karaoke), images.py
comfy/                   API-format workflow templates (to export), models.yaml, custom_nodes.txt, systemd unit
configs/                 all parameters (see above)
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
| music | none (Islamic) / ACE-Step 1.5 (memes) | no instruments policy; LTX's diegetic audio carries ambience |
| LLM | Claude Opus 5.5 ($4/$20 per MTok) | ≈ $0.18 per script; citations grounded in the corpus |

Excluded on license grounds: MiniMax H3 and HunyuanVideo 1.5 (territory restrictions incl. Korea),
FLUX.1/2 dev (non-commercial), F5-TTS / Higgs / VibeVoice (research-only), MMAudio (NC).

## Cost

Local generation ≈ **$0.30-0.40 per reel** (≈ $0.20 Claude + a few cents of electricity) versus
$3-48 per reel for cloud video APIs. Time on the Mac today: ~18 min for 24 keyframes + ~2 min for
narration, captions and assembly. On the 3090s the plan budgets ~40-50 min per reel including
twelve LTX-2.5 clips. Realistic revenue for a new account is near zero for 3-6 months; see the plan
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
| Wikipedia 403 | set a descriptive `VGI_HTTP_UA` (Wikimedia's user-agent policy) |
| `plan changed after approval` | `vgi approve <job>` again (the hash protects you from rendering an unreviewed edit) |

## Roadmap

1. **Phase 3** Linux render farm: ComfyUI × 2, LTX-2.5 workflows, benchmark seconds/clip.
2. Real Claude runs with the corpus; Fish Drama 3 behind the GPU lease; Claude-vision candidate pick.
3. Memes track end to end with ACE-Step beds; Korean-language track (Qwen3-TTS / ElevenLabs).
4. v2 publishing: Cloudflare R2 + Instagram API with Instagram Login, Trial Reels, 1-2 posts/day cron.
