"""The Demucs split on speech: the voice stays in the voices layer and the effects and music stay out of it. Real separator, a real (synthesized) voice, a take made at known
levels. Skipped where Windows' speech voices or Demucs are missing. See tests/speech_check.py for what this does and does not show."""
import os
import shutil
import tempfile

import numpy as np
import pytest

from tests import speech_check as SC

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not SC.available(), reason="needs Windows speech voices and Demucs")]


@pytest.fixture(scope="module")
def root():
    d = tempfile.mkdtemp(prefix="pf-speech-test-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def parts(root):
    sp = SC.speech_clips(root)
    n = int(8.5 * SC.RATE)
    return sp, SC.sfx(n, np.random.default_rng(7)) * 0.7 + SC.music(n) * 0.7


def test_speech_stays_in_the_voices_layer_when_effects_and_music_play_under_it(root, parts):
    sp, bed = parts
    r = SC.run(root, "a", sp["david"], bed, -6)
    assert r["speech_kept_in_voice"] > 0.8                 # measured 0.95 when this was written
    assert r["speech_leaked_to_other"] < 0.1               # measured 0.02
    assert r["bed_leaked_to_voice"] < 0.05                 # measured 0.005: the effects do not end up in the voices


def test_it_still_holds_when_the_bed_is_as_loud_as_the_speech(root, parts):
    sp, bed = parts
    r = SC.run(root, "b", sp["zira"], bed, 0)
    assert r["speech_kept_in_voice"] > 0.8                 # measured 0.92
    assert r["speech_leaked_to_other"] < 0.1               # measured 0.007
    assert r["bed_kept_in_other"] > 0.5                    # measured 0.80: most of the bed is where it should be


def test_a_take_with_only_speech_leaves_the_effects_layer_nearly_empty(root, parts):
    sp, _ = parts
    r = SC.run(root, "c", sp["david"], np.zeros(0, np.float32), 0)
    assert r["speech_kept_in_voice"] > 0.9                 # measured 0.99
    assert r["other_rms_db"] < r["voice_rms_db"] - 5       # measured 8.5 dB lower


def test_a_take_with_no_speech_keeps_its_effects_out_of_the_voices_layer(root, parts):
    _, bed = parts
    r = SC.run(root, "d", np.zeros(0, np.float32), bed, 0)
    assert r["bed_kept_in_other"] > 0.8                    # measured 0.96
    assert r["voice_rms_db"] < r["other_rms_db"] - 8       # measured 13.6 dB lower
