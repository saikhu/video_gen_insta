# Workflow templates (API format)

Generated, not hand-exported: official templates from `Comfy-Org/workflow_templates` → the frontend's
`graphToPrompt()` → `scripts/ui_to_api.py` with the spec in `comfy/specs/<name>.json` (placeholder injection,
node deletion, required-placeholder check). Validated against ComfyUI 0.43 `/prompt`.

| file | placeholders |
|---|---|
| `image_z_image_turbo.json` | prompt, width, height, seed, steps, prefix |
| `video_ltx25_i2v.json` | image, prompt, negative, final_width, final_height, fps, frames, seed, prefix |
| `video_ltx25_flf2v.json` | image, last_image, prompt, negative, width, height, fps, frames, seed, prefix |

A numeric placeholder that is the whole value becomes a number when filled (`fill_workflow`). `prefix` is the
`filename_prefix` of the save node; the pipeline sets it per job/scene/GPU so instances never collide.
