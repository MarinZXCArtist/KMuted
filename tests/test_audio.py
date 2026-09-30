import numpy as np

from kmuted.audio import dsp
from kmuted.audio.engine import MixerCore


def test_resample_lengths():
    x = np.sin(np.linspace(0, 10, 24000)).astype(np.float32)
    assert len(dsp.resample(x, 24000, 48000)) == 48000
    assert len(dsp.resample(x, 24000, 22050)) == 22050
    assert dsp.resample(x, 24000, 24000) is x or np.array_equal(dsp.resample(x, 24000, 24000), x)


def test_to_mono_float_from_int16_stereo():
    data = np.array([[32767, -32767], [16384, 16384]], dtype=np.int16)
    mono = dsp.to_mono_float(data)
    assert mono.dtype == np.float32
    assert np.allclose(mono, [0.0, 0.5], atol=1e-3)


def test_trim_silence_keeps_speech():
    sr = 1000
    x = np.concatenate([np.zeros(500), np.ones(100) * 0.5, np.zeros(400)]).astype(np.float32)
    y = dsp.trim_silence(x, sr, keep_ms=10)
    assert 100 <= len(y) <= 125
    assert dsp.trim_silence(np.zeros(100, dtype=np.float32), sr).size == 0


def test_prepare_clip_normalizes_overs():
    clip = dsp.prepare_clip(dsp.Clip(np.array([0.0, 2.0, -1.0, 0.0], dtype=np.float32), 4))
    assert np.max(np.abs(clip.samples)) <= 1.0


def test_mixer_plays_clips_in_order_and_reports_idle():
    events = []
    m = MixerCore(1000, 2, on_start=lambda: events.append("start"), on_idle=lambda: events.append("idle"))
    m.enqueue(dsp.Clip(np.full(30, 0.1, dtype=np.float32), 1000))
    m.enqueue(dsp.Clip(np.full(30, 0.2, dtype=np.float32), 1000))
    assert events == ["start"] and m.busy
    out = m.render(50)
    assert out.shape == (50, 2)
    assert np.allclose(out[:30, 0], 0.1) and np.allclose(out[30:50, 1], 0.2)
    out = m.render(50)
    assert np.allclose(out[:10], 0.2) and np.allclose(out[10:], 0.0)
    assert events == ["start", "idle"] and not m.busy
    m.render(10)
    assert events == ["start", "idle"]


def test_mixer_lead_silence_gain_and_clear():
    events = []
    m = MixerCore(1000, 1, on_idle=lambda: events.append("idle"))
    m.gain = 0.5
    m.enqueue(dsp.Clip(np.full(10, 1.0, dtype=np.float32), 1000), lead_ms=20)
    out = m.render(30)[:, 0]
    assert np.allclose(out[:20], 0.0) and np.allclose(out[20:], 0.5)
    m.enqueue(dsp.Clip(np.full(100, 1.0, dtype=np.float32), 1000))
    m.clear()
    assert np.allclose(m.render(10), 0.0)
    assert events == ["idle", "idle"]


def test_mixer_resamples_to_device_rate():
    m = MixerCore(2000, 1)
    m.enqueue(dsp.Clip(np.full(100, 0.3, dtype=np.float32), 1000))
    out = m.render(250)[:, 0]
    assert np.count_nonzero(out) == 200


def test_passthrough_mixes_and_drops_backlog():
    m = MixerCore(1000, 1)
    m.passthrough_gain = 1.0
    m.push_passthrough(np.full(10, 0.25, dtype=np.float32))
    assert np.allclose(m.render(20), 0.0)  # not enough buffered yet: wait
    m.push_passthrough(np.full(10, 0.25, dtype=np.float32))
    assert np.allclose(m.render(20), 0.25)
    for _ in range(40):  # 400 ms backlog > 250 ms max
        m.push_passthrough(np.full(10, 0.1, dtype=np.float32))
    assert m._pt_len <= int(1000 * MixerCore.PASSTHROUGH_MAX_S)
    m.enqueue(dsp.Clip(np.full(10, 0.5, dtype=np.float32), 1000))
    out = m.render(10)[:, 0]
    assert np.allclose(out, 0.6)


def test_sounds_overlap_speech_and_can_be_stopped():
    events = []
    m = MixerCore(1000, 1, on_start=lambda: events.append("start"), on_idle=lambda: events.append("idle"))
    m.enqueue(dsp.Clip(np.full(50, 0.1, dtype=np.float32), 1000))
    m.play_sound(np.full(30, 0.2, dtype=np.float32), 1000, "boom")
    m.play_sound(np.full(100, 8192, dtype=np.int16), 1000, "music")  # int16 source
    out = m.render(20)[:, 0]
    assert np.allclose(out, 0.1 + 0.2 + 0.25, atol=1e-3)
    assert m.playing_tags() == {"boom", "music"}
    m.stop_sounds("music")
    assert m.playing_tags() == {"boom"}
    m.render(40)  # boom ends at 30, speech at 50
    assert events == ["start", "idle"] and not m.busy


def test_sound_restart_and_mute_and_level():
    m = MixerCore(1000, 1)
    m.play_sound(np.full(100, 0.5, dtype=np.float32), 1000, "a")
    m.render(50)
    m.play_sound(np.full(100, 0.5, dtype=np.float32), 1000, "a")  # restart, not doubled
    out = m.render(10)[:, 0]
    assert np.allclose(out, 0.5)
    assert abs(m.level - 0.5) < 1e-6
    m.muted = True
    assert np.allclose(m.render(10), 0.0)
    assert m.level == 0.0
