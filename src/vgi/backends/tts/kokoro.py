"""Kokoro-82M TTS (Apache). Returns audio + word timings from the engine (no forced alignment needed)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ...core.models import WordTiming


def apply_lexicon(text: str, lexicon: dict) -> str:
    """Kokoro/misaki inline override: [Term](/ipa/)."""
    for term, entry in sorted(lexicon.items(), key=lambda kv: -len(kv[0])):
        ipa = (entry or {}).get("ipa")
        if not ipa:
            continue
        text = re.sub(rf"(?<![\w\[])({re.escape(term)})(?![\w\]])", rf"[\1](/{ipa}/)", text)
    return text


class KokoroTTSBackend:
    name = "kokoro"

    def __init__(self, voice: str = "bm_george", lang_code: str = "b", speed: float = 1.0, device: str = "cpu",
                 lexicon: dict | None = None):
        self.voice, self.lang_code, self.speed, self.device = voice, lang_code, speed, device
        self.lexicon = lexicon or {}
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from kokoro import KPipeline  # heavy import, lazy

            self._pipe = KPipeline(lang_code=self.lang_code, device=self.device if self.device != "cpu" else None)
        return self._pipe

    NATIVE_SR = 24000

    def synthesize(self, text: str, out_wav: Path, sample_rate: int = 24000, **_) -> tuple[float, list[WordTiming]]:
        import soundfile as sf

        sample_rate = self.NATIVE_SR   # Kokoro always emits 24 kHz; assembly resamples to the reel rate

        pipe = self._pipeline()
        chunks: list[np.ndarray] = []
        words: list[WordTiming] = []
        offset = 0.0
        for result in pipe(apply_lexicon(text, self.lexicon), voice=self.voice, speed=self.speed):
            audio = result.audio
            audio = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
            tokens = getattr(result, "tokens", None) or []
            for tk in tokens:
                st, en = getattr(tk, "start_ts", None), getattr(tk, "end_ts", None)
                txt = (getattr(tk, "text", "") or "").strip()
                if st is None or en is None or not txt:
                    continue
                if words and not re.search(r"\w", txt):  # punctuation token → attach to the previous word
                    words[-1].word += txt
                    words[-1].end = round(offset + float(en), 3)
                    continue
                words.append(WordTiming(word=txt, start=round(offset + float(st), 3), end=round(offset + float(en), 3)))
            chunks.append(audio)
            offset += len(audio) / sample_rate
        if not chunks:
            raise RuntimeError("Kokoro produced no audio")
        full = np.concatenate(chunks).astype(np.float32)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav), full, sample_rate)
        dur = len(full) / sample_rate
        if not words:  # engine gave no timestamps → even spacing fallback
            ws = [w for w in re.split(r"\s+", text.strip()) if w]
            step = dur / max(1, len(ws))
            words = [WordTiming(word=w, start=round(i * step, 3), end=round((i + 1) * step, 3)) for i, w in enumerate(ws)]
        return dur, words
