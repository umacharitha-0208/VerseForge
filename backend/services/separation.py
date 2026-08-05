import subprocess
import sys
from pathlib import Path

import torch

from backend.config import DEFAULT_STEM_COUNT, DEMUCS_MODELS, STEMS_DIR


class SeparationError(RuntimeError):
    pass


def separate_song(input_path: Path, stem_count: str = DEFAULT_STEM_COUNT) -> dict[str, Path]:
    """Run Demucs on input_path, return {stem_name: wav_path}. stem_count selects between the
    4-stem (vocals/drums/bass/other) and 6-stem (+guitar/piano) pretrained models."""
    if stem_count not in DEMUCS_MODELS:
        raise ValueError(f"Unknown stem_count {stem_count!r}, expected one of {list(DEMUCS_MODELS)}")
    model = DEMUCS_MODELS[stem_count]["name"]
    expected_stems = DEMUCS_MODELS[stem_count]["stems"]

    input_path = Path(input_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    track_name = input_path.stem

    cmd = [
        sys.executable, "-m", "demucs",
        "-n", model,
        "-d", device,
        "-o", str(STEMS_DIR),
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SeparationError(f"Demucs failed:\n{result.stdout}\n{result.stderr}")

    stem_dir = STEMS_DIR / model / track_name
    stems = {}
    for stem in expected_stems:
        path = stem_dir / f"{stem}.wav"
        if not path.exists():
            raise SeparationError(f"Expected stem not found: {path}")
        stems[stem] = path
    return stems
