# Workflow templates (API format)

Export each workflow from ComfyUI with **Workflow → Export (API)** and save it here with these names:

| file | purpose | placeholders the pipeline fills |
|---|---|---|
| `image_flux3_klein.json` | keyframes (Linux) | `{{prompt}} {{negative}} {{width}} {{height}} {{seed}} {{steps}} {{guidance}} {{prefix}}` |
| `image_qwen_2512.json` | keyframes alt | same |
| `video_ltx25_i2v.json` | clip from one keyframe | `{{image}} {{prompt}} {{negative}} {{seed}} {{frames}} {{width}} {{height}} {{steps}} {{fps}} {{prefix}}` |
| `video_ltx25_flf2v.json` | chained sub-clips | same + `{{last_image}}` |
| `video_wan22_i2v.json` | fallback video | same as i2v |
| `upscale_seedvr2.json` | optional upscale | `{{video}} {{prefix}}` |

Put a placeholder string (e.g. `"{{seed}}"`) in the node input you want controlled; numeric placeholders are
converted to numbers when the whole value is the placeholder. `SaveVideo`/`SaveImage` must use `{{prefix}}` as
`filename_prefix` so two instances never collide. Start from the ComfyUI templates `video_ltx2_5_i2v` and
`video_ltx2_5_flf2v` (docs.comfy.org/tutorials/video/ltx/ltx-2-5).
