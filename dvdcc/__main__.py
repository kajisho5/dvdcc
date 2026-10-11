"""Command line: `dvdcc VIDEO.m2v CAPTIONS [-o OUT] [--offset T] [--top]`."""

import argparse
import shutil
import sys

from . import __version__, captions
from .errors import CaptionError
from .subtitles import timecode_seconds


def _offset(value):
    try:
        return float(value)
    except ValueError:
        return timecode_seconds(value)


def main(argv=None):
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
