"""Splits Demucs' combined 'vocals' stem into an estimated lead vs. background vocal track.

This is a DSP heuristic (pitch-salience harmonic masking), not a dedicated trained model --
no lead/backing vocal separation model is available in this environment. It tracks the most
prominent, continuous pitch contour per frame (assumed to be the lead vocal's melody) with
librosa's pyin, builds a soft harmonic mask around that pitch and its overtones, and treats
the masked-in energy as 'lead' and the residual as 'background'. Quality depends heavily on
the mix: works best when there's one clear, dominant vocal line over more diffuse harmonies;
struggles on unison-doubled leads or when backing vocals are just as loud/tonal as the lead.
"""

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

N_FFT = 2048
HOP_LENGTH = 512
NUM_HARMONICS = 8
BANDWIDTH_SEMITONES = 0.5
VOICED_PROB_THRESHOLD = 0.1


def _fit_length(arr: np.ndarray, n: int, fill: float = np.nan) -> np.ndarray:
    if len(arr) == n:
        return arr
    if len(arr) > n:
        return arr[:n]
    return np.concatenate([arr, np.full(n - len(arr), fill)])


def split_lead_background(vocals_path: Path, out_dir: Path) -> dict[str, Path]:
    y, sr = librosa.load(str(vocals_path), sr=None, mono=True)

    stft = librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)
    magnitude, phase = np.abs(stft), np.angle(stft)
    n_frames = magnitude.shape[1]

    f0, _voiced_flag, voiced_prob = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"),
        sr=sr, frame_length=N_FFT, hop_length=HOP_LENGTH,
    )
    f0 = _fit_length(f0, n_frames)
    voiced_prob = _fit_length(voiced_prob, n_frames, fill=0.0)

    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    mask = np.zeros_like(magnitude)

    for frame_idx in range(n_frames):
        f0_val = f0[frame_idx]
        prob = voiced_prob[frame_idx]
        if not f0_val or np.isnan(f0_val) or prob < VOICED_PROB_THRESHOLD:
            continue
        for h in range(1, NUM_HARMONICS + 1):
            harmonic_freq = f0_val * h
            if harmonic_freq >= freqs[-1]:
                break
            low = harmonic_freq * (2 ** (-BANDWIDTH_SEMITONES / 12))
            high = harmonic_freq * (2 ** (BANDWIDTH_SEMITONES / 12))
            band = (freqs >= low) & (freqs <= high)
            # Binary within the harmonic band (rather than scaling by prob) -- a soft,
            # probability-weighted mask left too much of the lead's energy leaking into the
            # residual/background output.
            mask[band, frame_idx] = 1.0

    lead_mag = magnitude * mask
    background_mag = magnitude * (1 - mask)

    lead = librosa.istft(lead_mag * np.exp(1j * phase), hop_length=HOP_LENGTH, length=len(y))
    background = librosa.istft(background_mag * np.exp(1j * phase), hop_length=HOP_LENGTH, length=len(y))

    out_dir.mkdir(parents=True, exist_ok=True)
    lead_path = out_dir / "lead_vocals.wav"
    background_path = out_dir / "background_vocals.wav"
    sf.write(lead_path, lead, sr)
    sf.write(background_path, background, sr)
    return {"lead_vocals": lead_path, "background_vocals": background_path}
