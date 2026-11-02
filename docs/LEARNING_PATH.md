# Learning path: the technology inside `vgi`

A study guide for everything this project uses, in the order it makes sense to learn it. Each topic
says **why it is here**, **where it lives in the code**, **what to read** and a small **exercise** you can
run against the repo. Budget: roughly 4-6 weeks of evenings for the whole path; each level stands on
its own if you only need part of it.

Legend: ⏱ rough time · 📂 files to open · 📖 reading · 🧪 exercise

---

## Level 0 — Orientation (1 evening)

Run the pipeline once with stubs so every later topic has a concrete artifact to look at:

```bash
uv run vgi new --topic islamic_battles --subject "Battle of Uhud"
uv run vgi run <job> --dry-run
open outputs/jobs/<job>/04_storyboard/preview.html
```

Then read `README.md` (the diagram) and skim `outputs/jobs/<job>/manifest.json`. Everything below
explains one box of that diagram or one line of that manifest.

---

## Level 1 — Python engineering foundations

### 1.1 Modern packaging with `uv` and `pyproject.toml`  ⏱ 2 h
- **Why**: one lockfile, optional extras per backend (`[tts]`, `[mac]`, `[qa]`), pinned interpreter (`.python-version`).
- 📂 `pyproject.toml`, `.python-version`, `uv.lock`
- 📖 uv docs: *Projects* and *Python versions* (docs.astral.sh/uv). PEP 621 for `[project]` metadata.
- 🧪 Add an extra `[captions]` dependency and observe how `uv sync --extra captions` changes `uv.lock`.
  Explain why `pillow<13` is pinned (hint: `numbers._IntegralLike`).

### 1.2 Pydantic v2: schemas as the source of truth  ⏱ 3 h
- **Why**: every YAML block is validated (`STAGE_SCHEMAS`), every artifact has a contract (`ScenePlan`,
  `FactSheet`, `WordTiming`), and the same models become Claude's structured-output schema.
- 📂 `src/vgi/config/schemas.py`, `src/vgi/core/models.py`, `src/vgi/config/settings.py`
- 📖 Pydantic docs: *Models*, *Validators*, `ConfigDict(extra="allow")`, `model_dump`/`model_validate_json`;
  pydantic-settings for `.env` loading.
- 🧪 Add a `min_words` field to `ScriptCfg`, give it a validator, and make the script validator use it.

### 1.3 Typer CLIs and Rich output  ⏱ 1 h
- 📂 `src/vgi/cli.py`
- 📖 Typer tutorial (typer.tiangolo.com): commands, options, sub-apps (`corpus`, `models`).
- 🧪 Add `vgi show <job>` that prints the scene plan as a Rich table.

### 1.4 Configuration precedence and deep merges  ⏱ 2 h
- **Why**: hardware must beat content: `global < stage < topic < env < CLI`. Topic/env files override
  stage keys through a `stages:` block. A job freezes the *content* config but not the env.
- 📂 `src/vgi/config/loader.py` (`deep_merge`, `_apply_override`, `config_from_content`), `tests/test_config.py`
- 📖 Any article on layered configuration ("12-factor config"); Hydra's docs for how others solve it.
- 🧪 Break the precedence on purpose in a test and watch `test_env_beats_stage_and_topic` fail.

### 1.5 Idempotent pipelines: content hashing, caching, state machines  ⏱ 4 h
- **Why**: GPU minutes are expensive. A stage reruns only when an *output-determining* input changed.
  The approval hash makes the human gate tamper-evident.
- 📂 `src/vgi/core/stage.py` (`inputs`, `inputs_hash`, `execute`), `core/job.py` (`STATES`, `approve`,
  `invalidate_if_plan_changed`), `core/hashing.py` (`derive_seed`), `stages/keyframes.py::inputs`
- 📖 Make, Bazel or DVC docs on content-addressed caching; "Designing Data-Intensive Applications" ch. 10
  (batch processing, determinism). Luigi/Prefect task semantics for comparison.
- 🧪 Why does `KeyframesStage.inputs` exclude `keyframe_choice` while `VideoStage.inputs` includes the
  keyframe *file hash* and the *frame count* but not the audio hash? Write the two scenarios as tests.

### 1.6 Subprocesses, logging, failure semantics  ⏱ 2 h
- 📂 `src/vgi/media/ffmpeg.py::run`, `core/logging.py` (JSONL per stage), `backends/comfy_client.py`
  (timeouts, retries, `/interrupt`, `/free`, resume from `/history`)
- 📖 Python `subprocess` docs; "Release It!" (Nygard) chapters on timeouts and circuit breakers.
- 🧪 Add a `--timeout` option to `vgi render` that overrides `stages.video.timeout_seconds`.

---

## Level 2 — Audio and video engineering

### 2.1 ffmpeg fundamentals  ⏱ 6 h (the highest-leverage skill in this repo)
- **Why**: every segment, transition, caption burn, loudness pass and Ken Burns move is one ffmpeg command.
- 📂 `src/vgi/media/ffmpeg.py` — read `make_shot_segment`, `xfade_chain`, `finalize`, `ken_burns` with the
  filtergraph docs open.
- 📖 ffmpeg filters documentation (ffmpeg.org/ffmpeg-filters.html): `scale`, `crop`, `fps`, `tpad`,
  `xfade`, `aresample`, `zoompan`, `loudnorm`, `volume`, `alimiter`, `ass`. The "filtergraph syntax" section (labels `[v]`, chains, `;`).
- 🧪 Reproduce `xfade_chain` by hand for 3 clips and compute the offsets. Then change the transition to
  `wipeleft` and watch the result.

### 2.2 Containers, codecs and the Instagram spec  ⏱ 2 h
- **Why**: QA checks H.264 high profile, yuv420p, AAC 48 kHz 128 kbps, ≤25 Mbps, `moov` before `mdat`.
- 📂 `src/vgi/stages/qa.py`, `media/ffmpeg.py::stream_info`, `moov_before_mdat`
- 📖 Instagram Reels media spec (developers.facebook.com → Instagram platform → IG User Media);
  "faststart" and MP4 atoms (any MP4 structure primer); `ffprobe -show_streams`.
- 🧪 Remove `-movflags +faststart` in `finalize` and see QA fail with the moov message.

### 2.3 Loudness: EBU R128, LUFS and true peak  ⏱ 2 h
- **Why**: platforms normalize audio; −14 LUFS / −1 dBTP keeps narration consistent and un-clipped.
  `loudnorm` measures first (`print_format=json`); `finalize` then applies one static gain plus a limiter,
  because loudnorm's own second pass silently turns dynamic (and pumps) whenever the gain would clip.
- 📂 `media/ffmpeg.py::loudnorm_measure`, `linear_loudness`, `finalize`; `stages/qa.py` loudness block
- 📖 EBU Tech 3341/3342 summaries; ffmpeg `loudnorm` filter docs; an article on "why two-pass loudnorm".
- 🧪 Run the measurement on `final.mp4`, then on a scene WAV, and explain the difference between
  integrated loudness and true peak.

### 2.3a Sound design: spectrograms, HPSS, crossfades, ducking  ⏱ 4 h
- **Why**: LTX-2.5 makes a new soundtrack per clip. With 2-3 s shots that means a new soundscape at every cut,
  silent heads (holes at the cut) and an invented music drone (negative prompts do nothing at CFG 1).
  `media/sound.py` rebuilds one continuous location track: high-pass, harmonic/percussive separation to strip
  sustained tones, level matching, mirrored edges, equal-power crossfades that lead the cut (J-cut), a synthetic
  room tone, and a fixed gain envelope under the narration instead of a side-chain compressor.
- 📂 `src/vgi/media/sound.py`, `stages/assemble.py`, `configs/stages/assemble.yaml` (`sound:`), `tests/test_sound.py`
- 📖 Fitzgerald, "Harmonic/percussive separation using median filtering" (DAFx 2010); any primer on reading
  spectrograms; equal-power crossfades; J-cuts and L-cuts in film editing; room tone.
- 🧪 Render `ffmpeg -i final.mp4 -lavfi showspectrumpic=s=1600x500:fscale=log spec.png` before and after setting
  `demusic: false`, and find the horizontal lines (sustained tones) that the filter removes.

### 2.4 Subtitles: ASS/SSA and libass  ⏱ 3 h
- **Why**: karaoke captions (`\kf`), pop-in (`\fad`), styles with outline/shadow, `PlayResY` and
  `MarginV` to stay out of Instagram's UI overlays.
- 📂 `src/vgi/media/ass.py`, `configs/stages/captions.yaml`, `tests/test_captions.py`
- 📖 Aegisub ASS tags reference (aegisub.org/docs/latest/ass_tags); libass README; the `ass` ffmpeg filter.
- 🧪 Change `words_per_group` to 2 and `alignment` to 5 (center), render, and measure where the text
  lands versus `safe_zone` in `global.yaml`.

### 2.5 Timing arithmetic: frame grids, transitions, narration  ⏱ 2 h
- **Why**: LTX needs `8k+1` frames; segment length = lead-in + narration + tail (tail ≥ xfade so speech
  never straddles a transition); the caption timeline must subtract one xfade per cut.
- 📂 `media/ffmpeg.py::frames_for`, `stages/video.py::scene_seconds`, `stages/captions.py::timeline`
- 🧪 Derive the formula in `timeline()` from a 3-segment drawing, then verify with `08_captions/timeline.json`.

### 2.6 Ken Burns and motion from stills  ⏱ 1 h
- 📂 `media/ffmpeg.py::ken_burns`, `backends/video/ken_burns.py`
- 📖 `zoompan` filter docs; why pre-scaling (`pre_scale`) removes jitter.
- 🧪 Add a fourth pan direction (diagonal) and pick it by seed.

---

## Level 3 — Generative models (the GPU side)

### 3.1 Diffusion and flow-matching basics  ⏱ 6 h
- **Why**: to tune steps, guidance, seeds and resolution with intent instead of folklore. Z-Image
  Turbo is *guidance-distilled* (no CFG → negative prompts ignored); FLUX/Qwen-Image use guidance.
- 📖 Lilian Weng, "What are Diffusion Models?"; the Flow Matching paper (Lipman et al. 2022) for the
  intuition; Hugging Face Diffusers course (free) for hands-on; the Z-Image and FLUX model cards.
- 🧪 Generate the same prompt with seeds 1-4 and steps 4/8/12 through `mflux-generate-z-image-turbo`;
  note where quality stops improving (that is your `steps` setting).

### 3.2 Image generation on Apple Silicon: MLX and mflux  ⏱ 3 h
- **Why**: the Mac has no CUDA; MLX is Apple's array framework with unified memory. mflux ports FLUX,
  Qwen-Image, Z-Image to MLX with 8-bit quantization.
- 📂 `src/vgi/backends/image/mflux.py` (in-process cache, `_settle_output`), `docs/SETUP_MAC.md`
- 📖 MLX docs (ml-explore.github.io/mlx); mflux README; Apple's "unified memory" explainer.
- 🧪 Measure peak memory with `-q 4` vs `-q 8` and compare image quality on the same seed.

### 3.3 Video diffusion models: LTX-2.5, Wan 2.2, Kandinsky 6  ⏱ 4 h
- **Why**: I2V vs T2V, first/last-frame conditioning (FLF2V) for chaining long scenes, native audio
  generation, frame-count constraints, two-stage latent upscaling.
- 📂 `src/vgi/backends/video/comfy_video.py`, `stages/video.py::_generate_chained`, `comfy/models.yaml`
- 📖 LTX-2.5 model card and ComfyUI tutorial (docs.comfy.org/tutorials/video/ltx/ltx-2-5); Wan 2.2
  model card; Artificial Analysis video arena (how the ranking is built).
- 🧪 Draw the data flow of a 14-second scene through `_generate_chained` (which frame becomes the next
  first frame, why the seed is bumped).

### 3.4 Quantization and VRAM: fp16, fp8, INT8 ConvRot, GGUF  ⏱ 3 h
- **Why**: the 3090 (Ampere) has no fp8 tensor cores; INT8 ConvRot and GGUF Q8 are the right formats;
  NVFP4 needs Blackwell. Understanding this prevents buying the wrong model file.
- 📖 Hugging Face blog posts on quantization basics; ComfyUI-GGUF README; the ComfyUI changelog entry
  on INT8 ConvRot; NVIDIA Ampere vs Ada vs Blackwell datasheets (tensor core precision tables).
- 🧪 From `comfy/models.yaml`, compute the resident VRAM of the LTX-2.5 set and explain why the text
  encoder must be unloaded before sampling.

### 3.5 ComfyUI as a headless render server  ⏱ 4 h
- **Why**: workflows are JSON graphs; the API format is submitted to `POST /prompt`, progress arrives
  on `/ws`, results via `/history` and `/view`; one instance per GPU; `filename_prefix` keeps outputs apart.
- 📂 `src/vgi/backends/comfy_client.py` (`queue_prompt`, `wait`, `outputs`, `upload_image`, `free`),
  `comfy/workflows/README.md`, `comfy/systemd/comfy@.service`, `comfy/extra_model_paths.yaml`
- 📖 ComfyUI docs: *Server API examples* (docs.comfy.org/development/comfyui-server/api-examples);
  `script_examples/websockets_api_example.py` in the ComfyUI repo; comfy-cli README.
- 🧪 Export any ComfyUI workflow in API format, replace one input with `{{seed}}`, and run it through
  `fill_workflow` + `ComfyClient` from a Python shell.

### 3.6 Multi-GPU reality on consumer cards  ⏱ 1 h
- 📖 Raylight README (sequence/weight parallelism), ComfyUI-Distributed README, why DisTorch2 was
  archived. Decide when "two instances" beats "one model across two cards".

---

## Level 4 — Speech and language

### 4.1 Neural TTS: Kokoro, G2P and IPA  ⏱ 3 h
- **Why**: narration quality is the product. Kokoro-82M returns token timestamps (free captions),
  accepts inline IPA (`[Badr](/bædr/)`), and uses misaki for grapheme-to-phoneme with espeak fallback.
- 📂 `src/vgi/backends/tts/kokoro.py` (`apply_lexicon`, punctuation merge), `configs/pronunciation/lexicon.yaml`,
  `configs/voices/narrator_en.yaml`
- 📖 Kokoro-82M model card; misaki README (phoneme notation); an IPA chart for English; the Artificial
  Analysis TTS arena for how voices are compared.
- 🧪 Add `Yathrib` to the lexicon, synthesize a sentence, and check the returned word timings line up
  with what you hear.

### 4.2 Forced alignment and ASR (optional provider)  ⏱ 2 h
- **Why**: engines without timestamps (Fish Drama 3) need WhisperX alignment against the known script;
  the pronunciation QA compares ASR phonemes to the lexicon.
- 📖 WhisperX README (wav2vec2 alignment); the CTC forced-alignment tutorial in torchaudio.
- 🧪 Sketch `backends/align/whisperx.py` returning the same `WordTiming` contract as Kokoro.

### 4.3 Large language models through the Claude API  ⏱ 5 h
- **Why**: two call shapes carry Part A: *citations* (documents in the prompt, cited answer) and
  *structured outputs* (`messages.parse(output_format=PydanticModel)`), which cannot be combined.
  Adaptive thinking, effort levels, refusal fallbacks and cost accounting are all in the client.
- 📂 `src/vgi/llm/claude.py`, `llm/stub.py`, `core/cost.py`, `configs/pricing.yaml`, `topics/islamic_battles.py`
  (the system prompts are the real "spec" of the content)
- 📖 Claude docs: *Citations*, *Structured outputs*, *Extended/adaptive thinking*, *Pricing*,
  *Prompt caching* (platform.claude.com/docs). Anthropic's prompt-engineering guide.
- 🧪 With an API key, run `vgi plan` on Badr, read `01_research/fact_sheet.md`, then change
  `stages/research.yaml: effort` to `medium` and compare cost and citation density.

### 4.3b Local LLMs with Ollama  ⏱ 3 h
- **Why**: the default writer runs on your own GPUs: no API key, no per-call cost. Ollama serves GGUF models over
  HTTP; `format` = a JSON schema constrains the output to the Pydantic model; citations are emulated by numbering
  sources and mapping `[n]` markers back.
- 📂 `src/vgi/llm/local.py`, `configs/llm.yaml`, `scripts/ollama_serve.sh`, `vgi llm status|pull|test`
- 📖 Ollama API docs (`/api/chat`, `format`, `keep_alive`, `options.num_ctx`); a GGUF quantization primer;
  KV-cache memory math (layers × KV heads × head dim × context × 2 bytes).
- 🧪 Run `vgi llm test`, then compare the treatment from `qwen3.8:27b` and `gemma4:31b` for the same subject.

### 4.4 Grounding and retrieval (keeping history honest)  ⏱ 3 h
- **Why**: the corpus retrieval is deliberately simple (keyword-scored chunks with license headers);
  the LLM may only cite what it was given, and uncited claims must be hedged.
- 📂 `src/vgi/topics/base.py::corpus_chunks`, `data/corpus/islamic/README.md`, `cli.py::corpus_wikipedia`
- 📖 "Retrieval-augmented generation" survey (Lewis et al. 2020 for the origin); a chunking primer;
  Wikipedia's reuse/attribution rules (CC BY-SA 4.0).
- 🧪 Replace keyword scoring with embeddings (any small local model) and measure whether the fact
  sheet's citations improve for "Battle of Yarmouk".

### 4.5a Short-form storytelling and editing  ⏱ 4 h
- **Why**: retention is decided in the first 1.5 s and by cut rhythm. The craft rules (cold open, stakes, escalation,
  the turn, callback ending) and the beat/shot timeline encode this.
- 📂 `src/vgi/topics/craft.py`, `src/vgi/core/timeline.py`, `configs/stages/video.yaml` (pacing), `assemble.yaml` (`sound:`)
- 📖 Walter Murch, *In the Blink of an Eye* (why cuts work); any screenwriting primer on the three-act structure;
  J-cuts, room tone and dialogue ducking in film sound.
- 🧪 Change `pause_after` on the turn beat from 0.8 to 1.6 and `sound.duck_release_s` from 0.6 to 1.2; watch how the
  moment lands differently.

### 4.5 Prompt design for images and video  ⏱ 2 h
- 📂 `configs/styles/cinematic_desert.yaml`, `stages/keyframes.py::build_prompt`, the `visuals` list in `llm/stub.py`
- 📖 The FLUX and Z-Image prompting guides on their model cards; "shot types" vocabulary from any
  cinematography primer (aerial, wide, silhouette, close-up object).
- 🧪 Write a second style preset (e.g. `ink_wash`) and regenerate scene 7 under both.

---

## Level 5 — Policy, platforms and money

### 5.1 Content policy as code  ⏱ 2 h
- **Why**: depiction rules, honorifics, shot whitelists and banned characters are data in topic YAML,
  enforced by validators, the human gate and the YuNet face check.
- 📂 `configs/topics/*.yaml`, `topics/islamic_battles.py::validate`, `stages/qa.py::face_check`, `docs/POLICY.md`
- 📖 OpenCV YuNet model zoo page; Al-Azhar's position on depictions (referenced in `docs/POLICY.md`).
- 🧪 Lower `face_threshold` to 0.01 and see which scenes fail; argue for the right threshold.

### 5.2 Instagram Reels: specs, API and originality rules  ⏱ 2 h
- 📖 Instagram platform docs: *Content publishing*, *IG User Media* reference, changelog (`is_ai_generated`,
  Trial Reels); Instagram Creators blog on original content (April 2026); Meta's AI labeling posts.
- 🧪 Write the v2 `publish` stage on paper: container → poll → publish, with the exact spec checks QA
  already does.

### 5.3 Licensing for monetized AI content  ⏱ 2 h
- **Why**: "open weights" ≠ "commercial use"; some licenses exclude whole countries.
- 📖 The LICENSE files of LTX-2.5, FLUX 3 Klein (Kommunity), Fish Drama 3, Stability community license,
  MiniMax H3 (to see what an exclusion clause looks like), Apache 2.0 and MIT for contrast.
- 🧪 Make a one-page table: model → license → allowed here? → revenue cap → attribution/labeling duty.

### 5.4 Unit economics  ⏱ 1 h
- 📂 `core/cost.py`, `configs/pricing.yaml`, `metadata.json` of any exported job
- 🧪 Add electricity cost per reel to `metadata.json` using `env.power_watts` and the stage timings.

---

## Level 6 — Testing and operations

### 6.1 Testing media pipelines  ⏱ 2 h
- **Why**: stub backends make the whole DAG testable in 20 s with no GPU; math (frame grids, ASS
  margins, hashes) is unit-tested; the dry run is the integration test.
- 📂 `tests/`, `src/vgi/backends/stub.py`
- 📖 pytest docs (fixtures, `tmp_path`); "Working Effectively with Legacy Code" on seams.
- 🧪 Write the safe-zone render test described in the plan: render `captions.ass` over a black frame
  and assert no non-black pixels in the top 250 / bottom 420 px.

### 6.2 Running GPU services: systemd, SSH tunnels, model storage  ⏱ 2 h
- 📂 `comfy/systemd/comfy@.service`, `docs/SETUP_LINUX.md`, `configs/env/linux_2x3090.yaml`
- 📖 systemd template units (`%i`); `ssh -L` port forwarding; Hugging Face Hub CLI and `HF_TOKEN`.
- 🧪 Bring up one instance, tunnel it to the Mac, set `comfy.endpoints` in `env/mac_m5max.yaml`, and
  watch `vgi doctor` report VRAM.

---

## Suggested order and milestones

| week | focus | you can now |
|---|---|---|
| 1 | Level 0-1 | read any file in `src/vgi/` and explain why it exists |
| 2 | Level 2 | hand-write the ffmpeg commands the pipeline runs; change captions and transitions with intent |
| 3 | Level 3 | pick model files and quantizations for a given GPU; drive ComfyUI from Python |
| 4 | Level 4 | tune narration and prompts; run cited scripts with Claude and judge them |
| 5 | Level 5-6 | make policy and licensing decisions; extend tests; operate the render farm |

## Reference shelf (short)

- ffmpeg filters docs · Aegisub ASS tags · EBU R128 overview
- Lilian Weng "What are Diffusion Models?" · Flow Matching (Lipman 2022) · HF Diffusers course
- ComfyUI server API examples · comfy-cli · ComfyUI-GGUF · Raylight
- MLX docs · mflux README · Kokoro-82M card · misaki README · WhisperX README
- Claude docs: citations, structured outputs, adaptive thinking, pricing
- Instagram platform docs (content publishing, media spec, changelog) · Meta AI-labeling posts
- Model LICENSE files: LTX-2.5, FLUX 3 Klein, Fish Drama 3, Stability, MiniMax H3
