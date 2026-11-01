# Content policy encoded in the pipeline

**Islamic history track**
- Never depict the Prophet ﷺ, other prophets, his household or named Companions (Al-Azhar 2012 fatwa). Enforced by
  the topic negative prompt, the shot-type whitelist, the script validator, the human review gate and the QA face check.
- Narration speaks honorifics in full; captions render ﷺ / (RA) via `topics/islamic_battles.yaml: honorifics`.
- No instrumental music (`music_policy: native_only`). Numbers are hedged; contested events are avoided.
- Scripts cite the local corpus (public-domain / CC sources only). Copyrighted sira translations are reviewer reading, never ingested.

**Memes track**
- Original characters and premises only (`banned_characters`, Jaccard dedupe against `data/jokes_db.sqlite`).
- No religion, ethnicity, disability, sexual content, politics or real tragedies.

**Platform rules (verified 2026-11-02)**
- Every export carries the AI disclosure in the caption and `ai_generated: true` in metadata; set `is_ai_generated=true`
  when publishing via the Instagram API (v2). Korea's AI Basic Act (2026) targets providers but Meta requires the label.
- Instagram's originality rule (2026-04-30) demotes reposted content: generate, never scrape.
- Post 1-2 Reels/day. Use generated or licensed audio only.
