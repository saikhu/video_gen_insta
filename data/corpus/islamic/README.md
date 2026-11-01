# Islamic history corpus

Put plain-text or markdown source files here. Each file should start with a YAML-ish header:

```
---
title: Origins of the Islamic State (al-Baladhuri, tr. Hitti 1916)
license: public domain
url: https://archive.org/details/originsislamics00hittgoog
---
```

Public-domain / open sources (verified 2026-11-02): Hitti's Baladhuri translation (archive.org),
Muir's *Annals of the Early Caliphate* (Gutenberg #72386) and *Life of Mahomet* vol. 3 (archive.org),
Wikipedia (CC BY-SA 4.0, use `vgi corpus wikipedia "Battle of Badr"`), Al-Mawrid books (CC BY 4.0),
LearnSeerah (CC BY-SA 4.0). Copyrighted works (Guillaume, Tabari SUNY, Ibn Kathir, The Sealed Nectar,
Lings) must NOT be placed here; read them offline when reviewing scripts.

## What is checked in

Files named `wikipedia_*.md` are plain-text extracts fetched with `vgi corpus wikipedia "<title>"`
(CC BY-SA 4.0; each header carries the article URL, which is the attribution the license requires).
Files named `gutenberg_<id>_*.md` are public-domain books fetched with
`vgi corpus gutenberg <id> --title "..."`. Nothing copyrighted is stored here.
