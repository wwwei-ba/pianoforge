"""Verification figure: spectra of both tracks plus the two melody contours."""
from __future__ import annotations

import os

import numpy as np
import librosa

from . import analysis, melody


def verification_figure(y_orig, sr, y_piano, sr_p, mel_sig, metrics: dict, out_png: str,
                        title: str = "") -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = min(len(y_orig), len(y_piano))
    y1, y2 = y_orig[:n], y_piano[:n]
    ref = mel_sig[:n] if mel_sig is not None else y1

    h1, _ = analysis.hpss(ref, sr)
    h2, _ = analysis.hpss(y2, sr_p)
    m1 = melody.extract_melody(h1, sr, hop=256)
    m2 = melody.extract_melody(h2, sr_p, hop=256)

    fig = plt.figure(figsize=(15, 9), dpi=110)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.2, 1.2, 1.0], hspace=0.32)
    for sig, name, cell in ((y1, "original", gs[0]), (y2, "rendered piano", gs[1])):
        ax = fig.add_subplot(cell)
        S = np.abs(librosa.stft(sig, n_fft=2048, hop_length=512))
        D = librosa.amplitude_to_db(S, ref=np.max)
        ax.imshow(D, origin="lower", aspect="auto", cmap="magma", vmin=-70, vmax=0,
                  extent=[0, S.shape[1] * 512 / sr, 0, 11025])
        ax.set_ylim(0, 4000)
        ax.set_title(name, fontsize=10, loc="left")
        ax.set_ylabel("Hz")

    ax = fig.add_subplot(gs[2])
    ax.plot(m1["times"], m1["midi"], lw=1.0, color="#4c8bf5", label="original melody")
    ax.plot(m2["times"], m2["midi"], lw=1.0, color="#e8a33d", alpha=0.85,
            label="piano render melody")
    ax.set_ylim(50, 95)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("MIDI pitch")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.25)

    m = metrics
    txt = (f"pitch exact {m['melody_pitch_exact_pct']}%   within 1 semitone "
           f"{m['melody_pitch_within_semitone_pct']}%   octave errors "
           f"{m['melody_octave_error_pct']}%   contour r={m['melody_contour_corr']}\n"
           f"chroma similarity {m['chroma_similarity']}   score precision "
           f"{m['score_note_precision_pct']}%   recall {m['score_note_recall_pct']}%")
    fig.suptitle("PianoForge verification: " + title, fontsize=12)
    fig.text(0.5, 0.02, txt, ha="center", fontsize=9)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    return out_png
