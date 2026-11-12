"""Command line: `dvdcc VIDEO.m2v CAPTIONS [-o OUT] [--offset T] [--top]`,
`dvdcc check SUBTITLES [--json]` for what closed captions cannot carry as
written, and `dvdcc contract [--json]` for the machine-readable contract."""

import argparse
import json
import shutil
import sys

from . import __version__, captions
from .contract import contract
from .errors import CaptionError
from .subtitles import load_subtitles, timecode_seconds


def _offset(value):
    try:
        return float(value)
    except ValueError:
        return timecode_seconds(value)


def check_main(argv):
    p = argparse.ArgumentParser(
        prog="dvdcc check", description="Say, cue by cue, what of a subtitle file CEA-608 "
        "pop-on captions cannot carry as written (32 columns, 4 rows, the caption character "
        "set). Nothing is written.")
    p.add_argument("subtitles", help="subtitles: .srt, .vtt, .ass, .txt (text script)")
    p.add_argument("--json", action="store_true", help="the report as JSON")
    args = p.parse_args(argv)
    if args.subtitles.lower().endswith(".scc"):
        print(f"dvdcc: {args.subtitles} is a Scenarist file: its caption bytes are sent as "
              "they are, so there is nothing to check", file=sys.stderr)
        return 1
    try:
        cues = load_subtitles(args.subtitles)
    except CaptionError as e:
        print(f"dvdcc: {e.message}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"dvdcc: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    problems = captions.check(cues)
    if args.json:
        print(json.dumps({"file": args.subtitles, "cues": len(cues),
                          "cues_not_as_written": len({p["cue"] for p in problems}),
                          "limits": {"columns": captions.COLUMNS, "rows": captions.ROWS,
                                     "mode": "pop-on"},
                          "problems": problems}, indent=2, ensure_ascii=False))
        return 0
    for pr in problems:
        print(f"{args.subtitles}: {pr['message']}")
    bad = len({pr["cue"] for pr in problems})
    print(f"{args.subtitles}: {bad} of {len(cues)} cue(s) cannot be carried as written"
          if bad else f"{args.subtitles}: all {len(cues)} cue(s) fit closed captions")
    return 0


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if args in (["contract"], ["contract", "--json"]):
        print(json.dumps(contract(), indent=2))
        return 0
    if args[:1] == ["check"]:
        return check_main(args[1:])
    p = argparse.ArgumentParser(
        prog="dvdcc", description="Put line-21 closed captions (CEA-608, CC1) into the MPEG-2 "
        "video of a DVD (29.97 fps NTSC), without re-encoding it.")
    p.add_argument("--version", action="version", version=f"dvdcc {__version__}")
    p.add_argument("video", help="an MPEG-2 video elementary stream (.m2v)")
    p.add_argument("captions", help="a Scenarist .scc file, or subtitles: .srt, .vtt, .ass, "
                                    ".txt (text script)")
    p.add_argument("-o", "--output", help="write here (default: change the video in place)")
    p.add_argument("--offset", type=_offset, default=0.0,
                   help="taken off every time: seconds, or a timecode such as 01;00;00;00")
    p.add_argument("--top", action="store_true", help="subtitles' captions at the top")
    args = p.parse_args(argv)
    try:
        schedule, notes = captions.load(args.captions, args.offset,
                                        "top" if args.top else "bottom")
        target = args.output or args.video
        if args.output:
            shutil.copyfile(args.video, args.output)
        frames = captions.inject_file(target, schedule)
    except (CaptionError, ValueError) as e:
        print(f"dvdcc: {getattr(e, 'message', e)}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"dvdcc: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    for n in notes:
        print(f"dvdcc: note: {n}", file=sys.stderr)
    print(f"{target}: captions over {frames} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
