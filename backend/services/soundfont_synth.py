"""Sample-based instrument synthesis via FluidSynth + a General MIDI SoundFont (FluidR3_GM.sf2)
-- real recorded/multisampled instrument audio, not hand-rolled DSP. Replaces the earlier pure
synthesis engine for guitar: that could only ever approximate a real instrument's timbre from
first principles (oscillators, physical models) and, per user testing, didn't convincingly
sound like the real thing. FluidSynth renders actual sampled recordings instead.

Trade-off: a text description can no longer invent arbitrary timbre -- it now picks among a
curated list of real GM guitar articulations plus expression parameters (velocity/vibrato)
that soundfont playback actually supports.
"""

import json
import os
import re
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.config import FLUIDSYNTH_DLL_DIR, SOUNDFONT_PATH
from backend.services import llama_llm

SAMPLE_RATE = 44100
NOTE_DURATION_SEC = 2.0
MIDI_LOW = 36
MIDI_HIGH = 95

# General MIDI program numbers (0-indexed) relevant to each family, with human-readable names
# for the LLM prompt. Bank is always 0 (the standard GM bank) for this soundfont.
GM_PROGRAMS = {
    "guitar": {
        24: "Acoustic Guitar (nylon) -- warm, mellow, classical/fingerstyle",
        25: "Acoustic Guitar (steel) -- bright, crisp, folk/strummed",
        26: "Electric Guitar (jazz) -- warm, round, clean hollow-body tone",
        27: "Electric Guitar (clean) -- bright clean electric",
        28: "Electric Guitar (muted) -- percussive, palm-muted",
        29: "Overdriven Guitar -- gritty, driven rock tone",
        30: "Distortion Guitar -- heavy, saturated, aggressive",
        31: "Guitar Harmonics -- bell-like, chiming",
    },
}

FAMILY_DEFAULTS = {
    "guitar": {"program": 25, "velocity": 100, "vibrato_depth_cents": 0, "vibrato_rate_hz": 0.0},
}

_synth = None
_sfid = None
# Instrument-creation jobs run as FastAPI background tasks, which Starlette executes in a
# thread pool -- multiple instruments can be requested at once, but a single FluidSynth engine
# instance is not safe to drive concurrently from multiple threads (concurrent noteon/
# get_samples/noteoff calls corrupted native memory and crashed the process). This lock
# serializes ALL engine access, both lazy init and per-note synthesis.
_lock = threading.Lock()


def _get_synth():
    """Lazily loads the FluidSynth engine + SoundFont once per process -- the SoundFont is
    ~140MB and loading it is comparatively slow, so this must not happen per-note. Caller must
    hold _lock."""
    global _synth, _sfid
    if _synth is None:
        if not SOUNDFONT_PATH.exists():
            raise RuntimeError(f"SoundFont not found at {SOUNDFONT_PATH}")
        dll_dir = str(FLUIDSYNTH_DLL_DIR)
        if hasattr(os, "add_dll_directory") and Path(dll_dir).is_dir():
            os.add_dll_directory(dll_dir)
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        import fluidsynth

        synth = fluidsynth.Synth(samplerate=SAMPLE_RATE)
        _sfid = synth.sfload(str(SOUNDFONT_PATH))
        _synth = synth
    return _synth, _sfid


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    return json.loads(match.group(0))


def interpret_description(description: str, family: str) -> dict:
    """Falls back to FAMILY_DEFAULTS if the LLM call fails, is unparseable, or picks a program
    number outside the allowed list for this family -- the instrument still gets created with
    a sane default patch rather than failing outright."""
    programs = GM_PROGRAMS[family]
    program_list = "\n".join(f"{num}: {desc}" for num, desc in programs.items())
    prompt = (
        f"You are picking a real instrument patch and playing style for a {family} instrument "
        "based on a text description. Choose the BEST-matching program number from this exact "
        f"list (you may only use these numbers):\n{program_list}\n\n"
        "Respond with ONLY a JSON object with these exact keys:\n"
        '{"program": <one of the integers listed above>, '
        '"velocity": <1-127, how hard the string is picked/bowed -- higher = louder/more '
        'aggressive attack>, '
        '"vibrato_depth_cents": <0-100, pitch wobble amount -- 0 for none>, '
        '"vibrato_rate_hz": <0-8, speed of the pitch wobble>}\n\n'
        f"Description: {description}"
    )
    try:
        text = llama_llm.complete(prompt)
        parsed = _extract_json(text)
        params = {**FAMILY_DEFAULTS[family], **parsed}
        if int(params.get("program", -1)) not in programs:
            params["program"] = FAMILY_DEFAULTS[family]["program"]
        return params
    except Exception:
        return dict(FAMILY_DEFAULTS[family])


def synthesize_note(
    params: dict, midi_note: int, duration_sec: float = NOTE_DURATION_SEC, sr: int = SAMPLE_RATE
) -> np.ndarray:
    program = int(params.get("program", 40))
    velocity = int(min(max(params.get("velocity", 90), 1), 127))
    vibrato_depth = float(params.get("vibrato_depth_cents", 0.0))
    vibrato_rate = float(params.get("vibrato_rate_hz", 0.0))

    with _lock:
        synth, sfid = _get_synth()
        synth.program_select(0, sfid, 0, program)
        synth.noteon(0, midi_note, velocity)

        chunks = []
        if vibrato_depth > 0 and vibrato_rate > 0:
            # Apply pitch-bend vibrato in small chunks -- fluidsynth's pitch wheel range
            # defaults to +/-2 semitones (200 cents) of full deflection. NOTE: pyfluidsynth's
            # Synth.pitch_bend(chan, val) computes val+8192 internally (it wants a SIGNED
            # offset from center, not the raw 0-16383 wheel position) -- passing an
            # already-centered value here double-added 8192, clamping the bend to its maximum
            # for nearly the whole note, and even the "reset to center" call at the end
            # actually left the channel pinned near max bend, corrupting every note played
            # afterwards (reproduced: a plain, no-vibrato guitar note played right after a
            # vibrato'd violin note came out sharp too, until this was fixed).
            chunk_sec = 0.02
            n_chunks = max(int(duration_sec / chunk_sec), 1)
            t = 0.0
            for i in range(n_chunks):
                cents = vibrato_depth * np.sin(2 * np.pi * vibrato_rate * t)
                bend_offset = int((cents / 200.0) * 8192)
                bend_offset = min(max(bend_offset, -8192), 8191)
                synth.pitch_bend(0, bend_offset)
                chunks.append(synth.get_samples(int(chunk_sec * sr)))
                t += chunk_sec
            synth.pitch_bend(0, 0)
        else:
            chunks.append(synth.get_samples(int(duration_sec * sr)))

        synth.noteoff(0, midi_note)
        chunks.append(synth.get_samples(int(0.4 * sr)))  # release tail

    samples = np.concatenate(chunks).astype(np.float32)
    stereo = samples.reshape(-1, 2)
    mono = stereo.mean(axis=1) / 32768.0
    peak = np.max(np.abs(mono)) or 1.0
    mono = mono / peak * 0.9
    return mono.astype(np.float32)


def render_instrument(params: dict, out_dir: Path) -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = {}
    for midi in range(MIDI_LOW, MIDI_HIGH + 1):
        audio = synthesize_note(params, midi)
        path = out_dir / f"note_{midi}.wav"
        sf.write(path, audio, SAMPLE_RATE)
        notes[midi] = path
    return notes
