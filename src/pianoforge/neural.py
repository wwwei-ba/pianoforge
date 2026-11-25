"""Basic Pitch (Spotify, ICASSP 2022) transcription through ONNX Runtime.

The model sees 43,844 samples (1.99 s) of 22.05 kHz audio and returns note,
onset and contour activations for 88 piano keys; sliding windows are stitched
back into one timeline before note decoding.
"""
from __future__ import annotations

import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = os.path.join(ROOT, "bin", "models", "nmp.onnx")

WINDOW = 43844
HOP = 256 * 142          # keeps window starts aligned to the 256-sample frame grid
FRAME = 256
SESSION = None


def available() -> bool:
    return os.path.exists(MODEL)


def _session():
    global SESSION
    if SESSION is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
        SESSION = ort.InferenceSession(MODEL, sess_options=opts,
                                       providers=["CPUExecutionProvider"])
    return SESSION


def predict(y: np.ndarray, sr: int = 22050) -> tuple[np.ndarray, np.ndarray]:
    """Return (note, onset) activations shaped (88, frames) on the global frame grid."""
    import librosa

    if sr != 22050:
        y = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=22050)
    y = np.asarray(y, dtype=np.float32)
    sess = _session()
    n_frames = int(np.ceil(len(y) / FRAME)) + 2
    note = np.zeros((88, n_frames), dtype=np.float32)
    onset = np.zeros((88, n_frames), dtype=np.float32)
    weight = np.zeros(n_frames, dtype=np.float32)

    if len(y) < WINDOW:
        y = np.pad(y, (0, WINDOW - len(y)))
    starts = list(range(0, max(1, len(y) - WINDOW + 1), HOP))
    if not starts:
        starts = [0]
    if starts[-1] + WINDOW < len(y):
        starts.append(len(y) - WINDOW)

    for s in starts:
        chunk = y[s:s + WINDOW]
        if len(chunk) < WINDOW:
            chunk = np.pad(chunk, (0, WINDOW - len(chunk)))
        inp = chunk.reshape(1, WINDOW, 1)
        out = sess.run(None, {sess.get_inputs()[0].name: inp})
        # outputs: two (172, 88) maps and one (172, 264) contour; find which is onset
        maps = [o[0] for o in out if o.shape[-1] == 88]
        if len(maps) < 2:
            continue
        a, b = maps[0], maps[1]
        # the onset map is sharper in time: compare frame-to-frame variation
        def sharpness(m):
            return float(np.mean(np.abs(np.diff(m, axis=0))))
        if sharpness(a) > sharpness(b):
            on, no = a, b
        else:
            on, no = b, a
        base = s // FRAME
        for i in range(on.shape[0]):
            idx = base + i
            if idx >= n_frames:
                break
            note[:, idx] += no[i]
            onset[:, idx] += on[i]
            weight[idx] += 1.0

    weight[weight == 0] = 1.0
    return note / weight, onset / weight


def decode(note: np.ndarray, onset: np.ndarray, sr: int = 22050,
           onset_thresh: float = 0.5, note_thresh: float = 0.30,
           min_len: float = 0.09, min_midi: int = 21,
           sustain_start: float = 1.5, sustain_frames: int = 6) -> list[dict]:
    """Turn activations into a note list (times in seconds)."""
    hop_s = FRAME / float(sr)
    frames = note.shape[1]
    notes = []
    for p in range(88):
        n = note[p]
        o = onset[p]
        active = False
        start = 0
        quiet = 0
        for i in range(frames):
            if not active:
                # notes that started before the analysed span have no onset peak;
                # pick them up from a sustained run of note activation
                held = (i + sustain_frames <= frames
                        and n[i] >= note_thresh * sustain_start
                        and float(np.min(n[i:i + sustain_frames])) >= note_thresh)
                if (o[i] >= onset_thresh and n[i] >= note_thresh) or held:
                    active, start, quiet = True, i, 0
            else:
                if n[i] >= note_thresh * 0.7:
                    quiet = 0
                else:
                    quiet += 1
                    if quiet >= 3:
                        end = i - quiet + 1
                        if (end - start) * hop_s >= min_len:
                            notes.append({"pitch": p + min_midi,
                                          "start": start * hop_s,
                                          "end": end * hop_s,
                                          "strength": float(np.mean(o[start:end + 1]))})
                        active = False
        if active:
            end = frames
            if (end - start) * hop_s >= min_len:
                notes.append({"pitch": p + min_midi, "start": start * hop_s,
                              "end": end * hop_s,
                              "strength": float(np.mean(o[start:end]))})
    notes.sort(key=lambda x: (x["start"], x["pitch"]))
    return notes


def transcribe(y: np.ndarray, sr: int = 22050, **kw) -> list[dict]:
    note, onset = predict(y, sr)
    return decode(note, onset, sr=sr,
                  onset_thresh=float(kw.get("onset_thresh", 0.5)),
                  note_thresh=float(kw.get("note_thresh", 0.30)),
                  min_len=float(kw.get("min_len", 0.09)))
