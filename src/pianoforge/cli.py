"""Command line interface (Chinese / English)."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .i18n import LANGUAGES, get_language, set_language, tr


def _prescan_language(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pianoforge", description=tr("cli.desc"))
    ap.add_argument("--lang", choices=["zh", "en"], default=None, help=tr("cli.lang_help"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe", help=tr("cli.transcribe_help"))
    t.add_argument("audio")
    t.add_argument("--out", default=None, help=tr("cli.out_help"))
    t.add_argument("--sr", type=int, default=22050)
    t.add_argument("--title", default=None, help=tr("cli.title_help"))
    t.add_argument("--sep", action="store_true", default=True, help=tr("cli.sep_help"))
    t.add_argument("--no-sep", dest="sep", action="store_false", help=tr("cli.no_sep_help"))
    t.add_argument("--melody-lo", type=int, default=55, help=tr("cli.melody_lo_help"))
    t.add_argument("--melody-hi", type=int, default=96, help=tr("cli.melody_hi_help"))
    t.add_argument("--engine",
                   choices=["auto", "neural", "classic", "full", "piano", "six", "sixfull",
                            "max", "maxfull"],
                   default="auto")
    t.add_argument("--lang", choices=["zh", "en"], default=None, help=tr("cli.lang_help"))

    b = sub.add_parser("batch", help=tr("cli.batch_help"))
    b.add_argument("folder")
    b.add_argument("--out", default=None, help=tr("cli.out_help"))
    b.add_argument("--limit", type=int, default=0, help=tr("cli.limit_help"))
    b.add_argument("--lang", choices=["zh", "en"], default=None, help=tr("cli.lang_help"))
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = _prescan_language(argv)
    if lang:
        set_language(lang)
    else:
        get_language()

    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "lang", None):
        set_language(args.lang)

    from . import pipeline

    if args.cmd == "transcribe":
        try:
            rep = pipeline.run(args.audio, out_dir=args.out, sr=args.sr, title=args.title,
                               engine=args.engine,
                               use_separation=args.sep, melody_lo=args.melody_lo,
                               melody_hi=args.melody_hi)
        except ValueError as exc:
            print(tr("cli.input_error", err=exc))
            return 2
        print(json.dumps(rep["metrics"], indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "batch":
        import glob
        files = []
        for ext in ("*.ogg", "*.mp3", "*.wav", "*.flac", "*.m4a"):
            files.extend(glob.glob(os.path.join(args.folder, ext)))
        files.sort()
        if args.limit:
            files = files[: args.limit]
        rows = []
        for f in files:
            try:
                rep = pipeline.run(
                    f, out_dir=os.path.join(args.out or os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__)))), "out"),
                        os.path.basename(f)[:40]), sr=22050)
                rows.append((os.path.basename(f), rep["metrics"]))
            except Exception as exc:
                print(tr("cli.failed"), f, exc)
        print("\n" + tr("cli.summary"))
        for name, m in rows:
            print(f"{name[:40]:42s} chroma={m['chroma_similarity']:.3f} "
                  f"mel_ok={m['melody_pitch_exact_pct']:5.1f}% "
                  f"within1={m['melody_pitch_within_semitone_pct']:5.1f}%")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
