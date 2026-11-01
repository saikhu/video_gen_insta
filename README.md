# vgi — local AI video pipeline for Instagram Reels

Quality-first, fully local generation of 9:16 Reels: research → script → keyframes → **human review** → TTS →
video → captions → assembly → QA → export. Two topic tracks ship: `islamic_battles` (cited history) and `memes`
(original AI jokes). Runs on a MacBook Pro M5 Max (authoring, keyframe reels) and a Linux 2×RTX 3090 box
(render farm, ComfyUI). The research, model choices, policy constraints and cost verdict are in the plan file
(`~/.claude/plans/let-s-create-a-full-polymorphic-chipmunk.md`).

## Quick start (Mac)

```bash
uv sync --extra dev            # core + tests
uv sync --extra tts            # Kokoro narration (optional, ~300 MB)
cp .env.example .env           # add ANTHROPIC_API_KEY for real research/scripts (stub LLM otherwise)
uv run vgi doctor
uv run vgi corpus wikipedia "Battle of Badr"
uv run vgi new --topic islamic_battles --subject "Battle of Badr"
uv run vgi plan <job>          # Part A → outputs/jobs/<job>/04_storyboard/preview.html
uv run vgi pick <job> 3 1      # choose keyframe candidate 1 for scene 3 (optional)
uv run vgi approve <job>
uv run vgi render <job>        # Part B (Ken Burns clips until a ComfyUI endpoint is configured)
uv run vgi qa <job> && uv run vgi export <job>   # → 09_final/{<job>.mp4, cover.jpg, caption.txt, metadata.json}
```

`uv run vgi run <job> --dry-run` runs every stage with stub backends (no models, no API key) and produces a
placeholder reel; `uv run pytest` does the same inside the test suite.

## Parameter files

| file | controls |
|---|---|
| `configs/global.yaml` | reel spec (1080×1920, 25 fps, 45-75 s, −14 LUFS), safe zones, seed base |
| `configs/env/*.yaml` | per-machine backends and ComfyUI endpoints (**highest precedence**) |
| `configs/topics/*.yaml` | corpus, depiction policy, honorifics, music policy, hashtags, subjects |
| `configs/stages/*.yaml` | one file per stage (research, script, keyframes, video, tts, music, captions, assemble, qa, export, publish) |
| `configs/styles/*.yaml`, `voices/*.yaml`, `pronunciation/lexicon.yaml`, `pricing.yaml` | look, narrator voice, Arabic-name pronunciation, cost table |

Precedence: `global < stages/<stage> < topics/<topic> < env/<env> < --set key.path=value`. Topic and env files
override stage keys through a `stages:` block. A job freezes the content config (everything but env) at `vgi new`.

## Layout

`src/vgi/stages/*` one module per stage · `src/vgi/backends/*` ComfyUI / mflux / Kokoro / stub ·
`src/vgi/topics/*` topic plugins · `comfy/` workflow templates, model manifest, systemd unit ·
`outputs/jobs/<job>/` manifest.json + numbered stage folders + logs/*.jsonl · `docs/` setup guides.

## Policy baked in

No faces of sacred figures (prompt + QA face check), spoken honorifics in narration and ﷺ in captions, no
instruments for the Islamic track, original characters only for memes, AI disclosure in every caption and
`metadata.json` (`ai_generated: true`), 1-2 posts/day recommended. See `docs/POLICY.md`.
