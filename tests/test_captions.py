from vgi.core.models import WordTiming
from vgi.media.ass import build_ass, merge_honorifics


def _w(words, step=0.3):
    return [WordTiming(word=w, start=round(i * step, 3), end=round((i + 1) * step - 0.02, 3)) for i, w in enumerate(words)]


def test_honorific_merge_keeps_timing():
    words = _w(["the", "Prophet", "Muhammad,", "peace", "be", "upon", "him,", "led"])
    merged = merge_honorifics(words, [{"trigger": "peace be upon him", "caption": "ﷺ"}])
    assert [w.word for w in merged] == ["the", "Prophet", "Muhammad,", "ﷺ", "led"]
    assert merged[3].start == words[3].start and merged[3].end == words[6].end


def test_ass_has_margins_and_karaoke():
    ass = build_ass([(0.0, _w(["one", "two", "three", "four"]))], width=1080, height=1920, style={}, bottom_margin_px=420,
                    side_margin_px=60, words_per_group=3, pop_in_ms=80)
    assert "PlayResY: 1920" in ass
    assert ",60,60,420,1" in ass             # MarginL, MarginR, MarginV
    assert ass.count("Dialogue:") == 2 and "\\kf" in ass and "\\fad(80,0)" in ass
