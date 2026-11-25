"""Tempo, beats, key and chroma analysis."""
from __future__ import annotations

import numpy as np
import librosa


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler key profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def hpss(y: np.ndarray, sr: int, margin: float = 3.0):
    """Return (harmonic, percussive) with a softly masked split."""
    return librosa.effects.hpss(y, margin=margin)


def onset_envelope(y: np.ndarray, sr: int, hop: int = 512) -> np.ndarray:
    return librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)


def estimate_tempo_and_beats(y: np.ndarray, sr: int, hop: int = 512) -> dict:
    """Detect tempo and beat times; robust to lofi's soft transients."""
    oenv = onset_envelope(y, sr, hop)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=oenv, sr=sr, hop_length=hop, units="frames", trim=False
    )
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    # also compute a tempo estimate from the autocorrelation of the onset envelope
    ac = librosa.autocorrelate(oenv, max_size=min(len(oenv), 1200))
    bpm_range = np.arange(50, 200)
    lag = (60.0 * sr / hop) / bpm_range
    valid = lag < len(ac) - 1
    ac_tempo = float(bpm_range[valid][np.argmax(ac[lag[valid].astype(int)])]) if valid.any() else float(tempo)
    tempo_val = float(np.asarray(tempo).reshape(-1)[0])
    return {
        "tempo": tempo_val,
        "tempo_autocorr": ac_tempo,
        "beat_times": beat_times,
        "beat_frames": beat_frames,
        "onset_envelope": oenv,
        "hop": hop,
    }


def chroma_cqt(y: np.ndarray, sr: int, hop: int = 512) -> np.ndarray:
    c = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, n_chroma=12, bins_per_octave=36)
    return c


def estimate_key(chroma: np.ndarray) -> tuple[str, str, float]:
    """Return (tonic name, mode, score). Uses Krumhansl-Schmuckler correlation."""
    v = chroma.mean(axis=1)
    if v.sum() <= 0:
        return "C", "major", 0.0
    v = v - v.mean()
    best = ("C", "major", -2.0)
    for tonic in range(12):
        for mode, prof in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            p = np.roll(prof, tonic)
            p = p - p.mean()
            r = float(np.dot(v, p) / (np.linalg.norm(v) * np.linalg.norm(p) + 1e-9))
            if r > best[2]:
                best = (NOTE_NAMES[tonic], mode, r)
    return best


def beat_sync(feature: np.ndarray, beat_frames: np.ndarray) -> np.ndarray:
    if len(beat_frames) < 2:
        return feature
    return librosa.util.sync(feature, beat_frames, aggregate=np.median)


def estimate_beat_offset(beat_times: np.ndarray, duration: float) -> float:
    if len(beat_times) == 0:
        return 0.0
    return float(beat_times[0] % (60.0 / max(len(beat_times), 1) * 4)) if duration else 0.0


def dominant_pitch_class(chroma: np.ndarray) -> int:
    return int(np.argmax(chroma.mean(axis=1)))

def highpass(y: np.ndarray, sr: int, cutoff: float = 150.0, order: int = 4) -> np.ndarray:
    """Remove the bass register before melody tracking (bass harmonics fool it)."""
    from scipy.signal import butter, sosfilt
    if cutoff >= sr / 2:
        return y
    sos = butter(order, cutoff / (sr / 2), btype="highpass", output="sos")
    return sosfilt(sos, y).astype(np.float32)
