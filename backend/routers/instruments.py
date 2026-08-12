import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend import db
from backend.config import GENERATED_DIR
from backend.services import soundfont_synth
from backend.services.instrument_synth import (
    FAMILY_DEFAULTS,
    MIDI_HIGH,
    MIDI_LOW,
    interpret_description,
    render_instrument,
)
from backend.services.jobs import run_job

router = APIRouter(prefix="/api/instruments", tags=["instruments"])

# guitar is sample-based (real SoundFont recordings via FluidSynth) -- see soundfont_synth.py.
# "generic" is the only other family still on the pure-DSP oscillator engine
# (instrument_synth.py), kept as an internal fallback since its dedicated page was removed.
# ("violin" family removed entirely at the user's request.)
SOUNDFONT_FAMILIES = {"guitar"}


class InstrumentCreateIn(BaseModel):
    description: str
    title: str = ""
    family: str = "generic"
    webhook_url: str | None = None


def _cached_result(cached, family: str, midi_low: int, midi_high: int) -> dict:
    return {
        "instrument_id": cached["id"],
        "family": family,
        "params": json.loads(cached["params_json"]),
        "midi_low": midi_low,
        "midi_high": midi_high,
        "cached": True,
    }


def _do_create(description: str, title: str, family: str) -> dict:
    if family in SOUNDFONT_FAMILIES:
        cached = db.find_instrument_by_description(description, family)
        if cached and Path(cached["notes_dir"] or "").exists():
            return _cached_result(cached, family, soundfont_synth.MIDI_LOW, soundfont_synth.MIDI_HIGH)

        params = soundfont_synth.interpret_description(description, family)
        instrument_id = db.add_instrument(title, description, family, json.dumps(params), "")
        notes_dir = GENERATED_DIR / "instruments" / str(instrument_id)
        soundfont_synth.render_instrument(params, notes_dir)
        db.update_instrument_notes_dir(instrument_id, str(notes_dir))
        return {
            "instrument_id": instrument_id,
            "family": family,
            "params": params,
            "midi_low": soundfont_synth.MIDI_LOW,
            "midi_high": soundfont_synth.MIDI_HIGH,
            "cached": False,
        }

    family = family if family in FAMILY_DEFAULTS else "generic"
    cached = db.find_instrument_by_description(description, family)
    if cached and Path(cached["notes_dir"] or "").exists():
        return _cached_result(cached, family, MIDI_LOW, MIDI_HIGH)

    params = interpret_description(description, family)
    instrument_id = db.add_instrument(title, description, family, json.dumps(params), "")
    notes_dir = GENERATED_DIR / "instruments" / str(instrument_id)
    notes = render_instrument(params, notes_dir, family)
    db.update_instrument_notes_dir(instrument_id, str(notes_dir))
    return {
        "instrument_id": instrument_id,
        "family": family,
        "params": params,
        "midi_low": MIDI_LOW,
        "midi_high": MIDI_HIGH,
        "cached": False,
    }


@router.post("/create")
def create(payload: InstrumentCreateIn, background_tasks: BackgroundTasks):
    title_final = payload.title.strip() or "Untitled Instrument"
    job_id = db.create_job(
        "create_instrument",
        {"description": payload.description, "title": title_final, "family": payload.family},
        payload.webhook_url,
    )
    background_tasks.add_task(
        run_job, job_id, _do_create, payload.description, title_final, payload.family, heavy=True
    )
    return {"job_id": job_id}


@router.get("")
def list_instruments():
    return [dict(i) for i in db.list_instruments()]


@router.get("/{instrument_id}/notes")
def get_notes(instrument_id: int):
    instrument = db.get_instrument(instrument_id)
    if not instrument:
        raise HTTPException(404, "Instrument not found")
    notes_dir = Path(instrument["notes_dir"])
    notes = []
    for midi in range(MIDI_LOW, MIDI_HIGH + 1):
        path = notes_dir / f"note_{midi}.wav"
        if path.exists():
            notes.append({"midi": midi, "file_path": str(path)})
    return {"instrument": dict(instrument), "notes": notes, "midi_low": MIDI_LOW, "midi_high": MIDI_HIGH}
