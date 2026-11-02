"""Sound design: music stripping, continuous location track across cuts, envelope, loudness pass."""
import numpy as np

from vgi.config.schemas import SoundCfg
from vgi.media import sound
from vgi.media.ffmpeg import linear_loudness

SR = 16000


def _noise(seconds: float, seed: int, level: float = 0.05) -> np.ndarray:
    return (np.random.default_rng(seed).standard_normal((2, int(seconds * SR))) * level).astype(np.float32)


def _band_db(x: np.ndarray, f0: float) -> float:
    spec = np.abs(np.fft.rfft(x.mean(0))) ** 2
    f = np.fft.rfftfreq(x.shape[-1], 1 / SR)
    return 10 * np.log10(spec[(f > f0 - 5) & (f < f0 + 5)].sum() + 1e-12)


def test_demusic_strips_a_drone_but_keeps_noise():
    t = np.arange(2 * SR) / SR
    drone = sum(0.2 / k * np.sin(2 * np.pi * 220 * k * t) for k in range(1, 6)).astype(np.float32)
    noise = _noise(2, 1)
    x = noise + drone
    y = sound.demusic(x, SR)
    assert _band_db(x, 220) - _band_db(y, 220) > 15            # the sustained tone is gone
    keep = sound.active_rms_db(sound.demusic(noise, SR), SR) - sound.active_rms_db(noise, SR)
    assert keep > -8                                             # noise-like sound (wind) mostly survives


def test_layout_has_no_holes_at_cuts_even_with_silent_heads():
    cfg = SoundCfg()
    shots = []
    for i in range(4):
        a = _noise(2.3, i)
        a[:, : int(0.3 * SR)] = 0.0                              # LTX-style silent head
        s = sound.ShotSound(f"{i + 1}.1", start=i * 2.0, overlap=0.04, audio=a)
        sound.prepare_shot(s, SR, cfg, cfg.voice_db)
        assert s.info["used"] and s.info["head_s"] >= 0.28
        shots.append(s)
    loc = sound.layout(shots, 8.0, SR, cfg)
    assert sound.silent_gaps(loc, SR, skip_tail=cfg.end_fade_s) == []
    hard_cut = np.concatenate([np.pad(_noise(2.0, i)[:, int(0.3 * SR):], ((0, 0), (int(0.3 * SR), 0)))
                               for i in range(4)], axis=-1)
    assert sound.silent_gaps(hard_cut, SR) != []                 # the old hard-cut version does have holes


def test_too_quiet_shot_is_left_to_neighbours():
    cfg = SoundCfg()
    s = sound.ShotSound("1.1", 0.0, 0.0, _noise(2.0, 3, level=0.0003))
    sound.prepare_shot(s, SR, cfg, cfg.voice_db)
    assert not s.info["used"]


def test_envelope_rides_under_the_voice():
    env = sound.envelope(10 * SR, SR, [(2.0, 5.0)], gap_db=-7, under_db=-15, attack=0.25, release=0.6)
    lv = lambda t: 20 * np.log10(env[int(t * SR)])
    assert abs(lv(1.0) - -7) < 0.1 and abs(lv(3.5) - -15) < 0.1 and abs(lv(8.0) - -7) < 0.1
    assert -15 < lv(5.3) < -7                                      # release ramp after the line


def test_mix_puts_the_voice_on_top():
    cfg = SoundCfg()
    t = np.arange(3 * SR) / SR
    voice = (0.1 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)
    voice = np.stack([voice, voice])
    loc = _noise(8.0, 5, level=0.1)
    mix, rep = sound.mix_reel([(voice, 2.0)], loc, None, 8.0, SR, cfg, seed=1)
    assert mix.shape == (2, 8 * SR) and np.abs(mix).max() <= 0.9 + 1e-6
    under = sound.active_rms_db(mix[:, int(2.5 * SR): int(4.5 * SR)], SR)
    gap = sound.active_rms_db(mix[:, int(6.6 * SR): int(6.9 * SR)], SR)
    assert under - gap > 6 and rep["intervals"] == 1


def test_linear_loudness_is_a_static_gain_plus_limiter():
    af = linear_loudness(-20.5, -14.0, -1.0)
    assert af.startswith("volume=6.50dB,alimiter=") and "level=false" in af
