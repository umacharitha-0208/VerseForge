"""Text-to-instrument synthesis: an LLM interprets a text description into synth parameters,
then numpy/scipy render playable note samples across a wide pitch range. Implemented as
parametric synthesis rather than a generative-audio model, since no such model is available in
this environment.

- "generic": additive detuned oscillators + ADSR + filter + vibrato. Internal fallback family
  (used if an unrecognized family string is ever passed in) -- not exposed as its own page.
- "guitar": Karplus-Strong plucked-string physical model (a feedback delay line seeded with
  filtered noise), producing a natural pluck-and-decay character. Superseded by
  soundfont_synth.py's real sampled audio for the actual GuitarGPT page -- kept here only as
  the "generic" family's unreachable-but-harmless sibling, not otherwise used.

(A "violin" bowed-string DSP engine used to live here too; removed at the user's request after
repeated dissatisfaction with pure-synthesis violin -- GuitarGPT/ViolinGPT both moved to real
sampled audio (soundfont_synth.py), and the ViolinGPT page itself was removed entirely.)
"""

import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

from backend.services import llama_llm

SAMPLE_RATE = 44100
NOTE_DURATION_SEC = 2.0

# MIDI 36 (C2) .. MIDI 95 (B6): 60 notes / 5 octaves, wide enough for the keyboard UI's
# 36-key window to slide across via octave shift without re-rendering.
MIDI_LOW = 36
MIDI_HIGH = 95

FAMILY_DEFAULTS = {
    "generic": {
        "waveform": "sawtooth",
        "num_unison": 2,
        "detune_cents": 8,
        "attack": 0.01,
        "decay": 0.15,
        "sustain": 0.7,
        "release": 0.3,
        "filter_type": "lowpass",
        "filter_cutoff_hz": 4000,
        "vibrato_rate_hz": 5.0,
        "vibrato_depth_semitones": 0.0,
        "brightness": 0.5,
    },
    "guitar": {
        "damping": 0.6,
        "brightness": 0.5,
        "release": 0.15,
    },
}

# Distinct JSON schemas per family so the LLM is asked for parameters that actually matter
# for that synthesis engine, rather than reusing the oscillator schema for a physical model.
FAMILY_PROMPTS = {
    "generic": (
        '{"waveform": "sine"|"square"|"sawtooth"|"triangle"|"noise", '
        '"num_unison": <1-4 integer, detuned voices stacked for thickness>, '
        '"detune_cents": <0-25, spread between unison voices>, '
        '"attack": <seconds, 0.001-1.0>, "decay": <seconds, 0.01-1.5>, '
        '"sustain": <0-1, sustain level>, "release": <seconds, 0.05-2.0>, '
        '"filter_type": "lowpass"|"highpass"|"none", "filter_cutoff_hz": <200-12000>, '
        '"vibrato_rate_hz": <0-8>, "vibrato_depth_semitones": <0-0.5>, '
        '"brightness": <0-1, higher = more harmonic overtones mixed in>}'
    ),
    "guitar": (
        '{"damping": <0-1, 0=muted/quick decay, 1=long ringing sustain>, '
        '"brightness": <0-1, pluck attack sharpness/high-end content>, '
        '"release": <seconds, 0.05-0.5, final fade-out length>}'
    ),
}


def _midi_to_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    return json.loads(match.group(0))


def interpret_description(description: str, family: str = "generic") -> dict:
    """Falls back to FAMILY_DEFAULTS if the LLM call fails or returns unparseable output --
    the instrument still gets created, just with a generic default timbre for that family."""
    family = family if family in FAMILY_DEFAULTS else "generic"
    schema = FAMILY_PROMPTS[family]
    prompt = (
        "You are a sound designer translating a text description into synthesizer parameters "
        f"for a {family} instrument. Respond with ONLY a JSON object with these exact keys:\n"
        f"{schema}\n\nDescription: {description}"
    )
    try:
        text = llama_llm.complete(prompt)
        parsed = _extract_json(text)
        return {**FAMILY_DEFAULTS[family], **parsed}
    except Exception:
        return dict(FAMILY_DEFAULTS[family])


def _oscillator(waveform: str, freq: np.ndarray, t: np.ndarray) -> np.ndarray:
    phase = 2 * np.pi * freq * t
    if waveform == "sine":
        return np.sin(phase)
    if waveform == "square":
        return np.sign(np.sin(phase))
    if waveform == "sawtooth":
        return 2 * (t * freq - np.floor(0.5 + t * freq))
    if waveform == "triangle":
        return 2 * np.abs(2 * (t * freq - np.floor(0.5 + t * freq))) - 1
    if waveform == "noise":
        return np.random.uniform(-1, 1, size=t.shape)
    return np.sin(phase)


def _adsr_envelope(n_samples: int, sr: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    attack_n = max(int(attack * sr), 1)
    decay_n = max(int(decay * sr), 1)
    release_n = max(int(release * sr), 1)
    sustain_n = max(n_samples - attack_n - decay_n - release_n, 0)

    env = np.concatenate([
        np.linspace(0, 1, attack_n, endpoint=False),
        np.linspace(1, sustain, decay_n, endpoint=False),
        np.full(sustain_n, sustain),
        np.linspace(sustain, 0, release_n, endpoint=True),
    ])
    if len(env) < n_samples:
        env = np.pad(env, (0, n_samples - len(env)))
    return env[:n_samples]


def _apply_filter(signal: np.ndarray, filter_type: str, cutoff_hz: float, sr: int) -> np.ndarray:
    nyq = sr / 2
    cutoff = min(max(cutoff_hz, 50), nyq - 100) / nyq
    b, a = butter(2, cutoff, btype="low" if filter_type == "lowpass" else "high")
    return lfilter(b, a, signal)


def _synthesize_additive(params: dict, midi_note: int, duration_sec: float, sr: int) -> np.ndarray:
    freq = _midi_to_freq(midi_note)
    n_samples = int(duration_sec * sr)
    t = np.arange(n_samples) / sr

    vibrato = params.get("vibrato_depth_semitones", 0.0) * np.sin(
        2 * np.pi * params.get("vibrato_rate_hz", 0.0) * t
    )
    freq_mod = freq * (2.0 ** (vibrato / 12.0))

    num_unison = max(1, min(int(params.get("num_unison", 1)), 4))
    detune_cents = params.get("detune_cents", 0.0)
    waveform = params.get("waveform", "sine")

    mix = np.zeros(n_samples)
    for v in range(num_unison):
        spread = 0.0 if num_unison == 1 else (v / (num_unison - 1) - 0.5) * 2 * detune_cents
        voice_freq = freq_mod * (2.0 ** (spread / 1200.0))
        mix += _oscillator(waveform, voice_freq, t)
    mix /= num_unison

    brightness = params.get("brightness", 0.5)
    if brightness > 0 and waveform != "noise":
        overtone = _oscillator(waveform, freq_mod * 2, t) * brightness * 0.3
        mix = mix * (1 - brightness * 0.3) + overtone

    filter_type = params.get("filter_type", "none")
    if filter_type in ("lowpass", "highpass"):
        mix = _apply_filter(mix, filter_type, params.get("filter_cutoff_hz", 4000), sr)

    env = _adsr_envelope(
        n_samples, sr,
        params.get("attack", 0.01), params.get("decay", 0.15),
        params.get("sustain", 0.7), params.get("release", 0.3),
    )
    mix = mix * env

    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.9
    return mix.astype(np.float32)


def _synthesize_pluck(params: dict, midi_note: int, duration_sec: float, sr: int) -> np.ndarray:
    """Karplus-Strong: a short noise burst circulates through a delay line whose length sets
    the pitch; each pass through the loop gets averaged (low-pass) and scaled (damping),
    which is what produces the natural pluck-then-decay, brighter-then-duller character."""
    freq = _midi_to_freq(midi_note)
    n_samples = int(duration_sec * sr)
    period_samples = max(int(round(sr / freq)), 2)

    damping = min(max(float(params.get("damping", 0.6)), 0.0), 1.0)
    brightness = min(max(float(params.get("brightness", 0.5)), 0.0), 1.0)
    decay_factor = 0.9 + 0.099 * damping

    buf = np.random.uniform(-1.0, 1.0, period_samples)
    if brightness < 0.99:
        smooth_window = max(1, int(round((1 - brightness) * 6)) + 1)
        kernel = np.ones(smooth_window) / smooth_window
        buf = np.convolve(buf, kernel, mode="same")

    output = np.empty(n_samples, dtype=np.float64)
    idx = 0
    for i in range(n_samples):
        cur = buf[idx]
        output[i] = cur
        nxt = buf[(idx + 1) % period_samples]
        buf[idx] = decay_factor * 0.5 * (cur + nxt)
        idx = (idx + 1) % period_samples

    release = params.get("release", 0.15)
    release_n = max(int(release * sr), 1)
    if release_n < n_samples:
        fade = np.ones(n_samples)
        fade[-release_n:] = np.linspace(1, 0, release_n)
        output *= fade

    peak = np.max(np.abs(output)) or 1.0
    output = output / peak * 0.9
    return output.astype(np.float32)


def synthesize_note(
    params: dict,
    midi_note: int,
    duration_sec: float = NOTE_DURATION_SEC,
    sr: int = SAMPLE_RATE,
    family: str = "generic",
) -> np.ndarray:
    if family == "guitar":
        return _synthesize_pluck(params, midi_note, duration_sec, sr)
    return _synthesize_additive(params, midi_note, duration_sec, sr)


def render_instrument(params: dict, out_dir: Path, family: str = "generic") -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = {}
    for midi in range(MIDI_LOW, MIDI_HIGH + 1):
        audio = synthesize_note(params, midi, family=family)
        path = out_dir / f"note_{midi}.wav"
        sf.write(path, audio, SAMPLE_RATE)
        notes[midi] = path
    return notes
