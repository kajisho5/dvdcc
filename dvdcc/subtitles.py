"""Subtitle files read as cues: SubRip, WebVTT, ASS / SSA and text scripts
(number, start and end timecode, text), with drop-frame and non-drop
timecodes."""

import dataclasses
import os
import re
from dataclasses import dataclass

from .errors import CaptionError

_TIME = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")
_TAG = re.compile(r"</?[a-zA-Z][^>]*>|\{\\[^}]*\}")


@dataclass
class Cue:
    start: float
    end: float
    lines: list
    position: str = None   # "top" | "bottom" | None (the track's / default)
    color: str = None      # "#RRGGBB" fill colour from the cue itself, or None
    style_color: str = None  # the subtitle file's style colour (after the track's)
    image: str = None      # an image script's picture (absolute path): no text


_AN = re.compile(r"\\an?(\d)")
_ASS_COLOR = re.compile(r"\\1?c&H([0-9A-Fa-f]{2,8})&?")
_FONT_COLOR = re.compile(r'<font[^>]*color\s*=\s*"?#?([0-9A-Fa-f]{6})"?', re.I)


def _style_of(text):
    r"""(position, colour) from override tags in a cue's text: ASS-style {\an8}
    (also common in SRT) and {\c&HBBGGRR&}, or SRT <font color="#RRGGBB">."""
    pos = color = None
    for block in re.findall(r"\{([^}]*)\}", text):
        m = _AN.search(block)
        if m:
            n = int(m.group(1))
            # \an7-9 = top (numpad layout); the legacy \a5-7,9-11 also mean top
            pos = "top" if (n in (7, 8, 9) if "an" in block else n >= 5) else "bottom"
        m = _ASS_COLOR.search(block)
        if m:
            bgr = m.group(1)[-6:].rjust(6, "0")
            color = "#" + (bgr[4:6] + bgr[2:4] + bgr[0:2]).upper()
    m = _FONT_COLOR.search(text)
    if m:
        color = "#" + m.group(1).upper()
    return pos, color

def _t(m):
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text, vtt=False):
    """Parse SubRip (or, with vtt=True, WebVTT) text into a sorted list of
    non-overlapping Cues."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if vtt:
        text = _VTT_TIME.sub(lambda m: "00:" + m.group(0), text)   # MM:SS.mmm -> H:MM:SS.mmm
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        times = _TIME.findall(lines[idx])
        if len(times) < 2:
            raise ValueError(f"bad SRT timing line: {lines[idx]!r}")
        start = _t(_TIME.match(":".join(times[0][:3]) + "," + times[0][3]))
        end = _t(_TIME.match(":".join(times[1][:3]) + "," + times[1][3]))
        raw_body = lines[idx + 1:]
        pos, color = _style_of("\n".join(raw_body))
        if pos is None and vtt:
            m = re.search(r"\bline:(-?\d+(?:\.\d+)?)(%?)", lines[idx])
            if m:
                v = float(m.group(1))
                pos = "top" if (0 <= v < 50 if m.group(2) else 0 <= v < 6) else "bottom"
        body = [_TAG.sub("", l).strip() for l in raw_body]
        body = [l for l in body if l]
        if body and end > start:
            cues.append(Cue(start, end, body, pos, color))
    return _tidy(cues)


def _tidy(cues):
    cues.sort(key=lambda c: c.start)
    # a subpicture stream shows one image at a time: clip overlaps
    for a, b in zip(cues, cues[1:]):
        if a.end > b.start:
            a.end = b.start
    return [c for c in cues if c.end - c.start >= 0.04]


_VTT_TIME = re.compile(r"(?<![\d:])\d{1,2}:\d{2}\.\d{3}")


def parse_vtt(text):
    if not text.lstrip("\ufeff").startswith("WEBVTT"):
        raise ValueError("not a WebVTT file (no WEBVTT header)")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    keep = [b for b in blocks if "-->" in b]          # drop header, NOTE and STYLE blocks
    return parse_srt("\n\n".join(keep), vtt=True)


def parse_ass(text):
    """Dialogue lines of an ASS / SSA script (styles: alignment and colour)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    styles, fmt, sfmt, cues = {}, None, None, []
    section = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("["):
            section = line.lower()
            continue
        key, _, val = line.partition(":")
        if "styles" in section and key == "Format":
            sfmt = [x.strip().lower() for x in val.split(",")]
        elif "styles" in section and key == "Style" and sfmt:
            f = dict(zip(sfmt, [x.strip() for x in val.split(",", len(sfmt) - 1)]))
            align = int(f.get("alignment", "2") or 2)
            colour = f.get("primarycolour", "")
            styles[f.get("name", "")] = (
                "top" if align in (7, 8, 9) else None,
                _style_of("{\\c" + colour + "&}")[1] if colour.startswith("&H") else None)
        elif "events" in section and key == "Format":
            fmt = [x.strip().lower() for x in val.split(",")]
        elif "events" in section and key == "Dialogue" and fmt:
            f = dict(zip(fmt, [x.strip() for x in val.split(",", len(fmt) - 1)]))
            try:
                start = _t(_TIME.match(f["start"].replace(".", ",") + "0"))
                end = _t(_TIME.match(f["end"].replace(".", ",") + "0"))
            except (KeyError, AttributeError):
                raise ValueError(f"bad ASS dialogue line: {line[:60]!r}")
            raw = f.get("text", "")
            spos, scol = styles.get(f.get("style", ""), (None, None))
            pos, color = _style_of(raw)
            body = re.sub(r"\{[^}]*\}", "", raw).replace("\\h", " ")
            body = [l.strip() for l in re.split(r"\\[Nn]", body) if l.strip()]
            if body and end > start:
                cues.append(Cue(start, end, body, pos or spos, color, scol))
    if fmt is None:
        raise ValueError("no [Events] Format line: not an ASS / SSA script")
    return _tidy(cues)


# -- text scripts ---------------------------------------------------------------
# The plain subtitle script of disc authoring tools: a number, the start and
# end timecode, the text; lines after it (up to the next numbered line) are
# more lines of the same subtitle. Spaces or tabs between the fields.
#   1 00;00;02;02 00;00;03;15 The cat never came back.
#   She just walked away.
# Timecode: hh;mm;ss;ff is NTSC drop frame; hh:mm:ss:ff counts frames of 30
# (NTSC, non drop frame) or 25 (PAL); leading zeros may be left out. A time
# hh:mm:ss,mmm (or .mmm) is read too.
_TC = TIMECODE = re.compile(r"^(\d{1,2})([:;])(\d{1,2})([:;])(\d{1,2})([:;.,])(\d{1,3})$")
_SCRIPT_LINE = re.compile(r"^\s*(\d+)[ \t]+(\S+)[ \t]+(\S+)(?:[ \t]+(.*))?$")
# an image script: the same lines with a picture file instead of the text
#   1 00;00;02;02 00;00;03;15 sub0001.png
IMAGE_FILE = re.compile(r"\.(png|bmp|tiff?|jpe?g|webp)$", re.I)


def timecode_seconds(tc, standard="NTSC"):
    """Seconds from a timecode of the disc's `standard`."""
    m = _TC.match(str(tc).strip())
    if not m:
        raise ValueError(f"{tc!r} is not a timecode (hh;mm;ss;ff or hh:mm:ss:ff)")
    h, mi, s, last, f = int(m[1]), int(m[3]), int(m[5]), m[6], m[7]
    if mi > 59 or s > 59:
        raise ValueError(f"{tc!r}: minutes and seconds go to 59")
    if last in ".,":
        return h * 3600 + mi * 60 + s + int(f.ljust(3, "0")) / 1000
    f = int(f)
    drop = ";" in (m[2], m[4], last)
    base = 30 if drop or standard == "NTSC" else 25
    if f >= base:
        raise ValueError(f"{tc!r}: frame {f} of {base}")
    frames = (h * 3600 + mi * 60 + s) * base + f
    if drop:
        # two frame numbers are left out every minute, except every tenth
        minutes = h * 60 + mi
        frames -= 2 * (minutes - minutes // 10)
    return frames * 1001 / 30000 if base == 30 else frames / 25


def seconds_timecode(t, standard="NTSC"):
    """The timecode of a moment: drop frame on NTSC (;), frames of 25 on PAL (:)."""
    if standard != "NTSC":
        frames = int(round(t * 25))
        f, s = frames % 25, frames // 25
        return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"
    frames = int(round(t * 30000 / 1001))
    # (drop frame: 17982 frames per ten minutes, 1798 in each but the first minute)
    tens, rest = divmod(frames, 17982)
    frames += 18 * tens + (2 * ((rest - 2) // 1798) if rest > 1 else 0)
    f, s = frames % 30, frames // 30
    return f"{s // 3600:02d};{s // 60 % 60:02d};{s % 60:02d};{f:02d}"


def parse_text_script(text, standard="NTSC", base=None):
    """Cues of a text script. With `base` (the script's folder), a subtitle
    whose text is just a picture file's name (relative to it) is that
    picture: an image script."""
    cues, cur = [], None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = _SCRIPT_LINE.match(line)
        if m and _TC.match(m[2]) and _TC.match(m[3]):
            try:
                start, end = timecode_seconds(m[2], standard), timecode_seconds(m[3], standard)
            except ValueError as e:
                raise ValueError(f"line {n}: {e}")
            if end <= start:
                raise ValueError(f"line {n}: subtitle {m[1]} ends before it starts")
            cur = Cue(start, end, [m[4].strip()] if m[4] and m[4].strip() else [])
            cues.append(cur)
        elif line and cur is not None:
            cur.lines.append(line)
        elif line:
            raise ValueError(f"line {n}: expected \"number start end text\", got {line[:40]!r}")
    if not cues:
        raise ValueError("no subtitles (lines of number, start and end timecode, text)")
    if base is not None:
        for n, c in enumerate(cues, 1):
            if len(c.lines) == 1 and IMAGE_FILE.search(c.lines[0]):
                path = os.path.normpath(os.path.join(base, c.lines[0]))
                if not os.path.isfile(path):
                    raise ValueError(f"subtitle {n}: picture {c.lines[0]!r} not found next to "
                                     "the script")
                c.image, c.lines = path, []
    return _tidy([c for c in cues if c.lines or c.image])


def to_text_script(cues, standard="NTSC"):
    """Cues -> a text script (no positions or colours: a script has none)."""
    out = []
    for n, c in enumerate(cues, 1):
        # (a picture: its file name, as an image script has it)
        lines = [os.path.basename(c.image)] if c.image else list(c.lines) or [""]
        out.append(f"{n}\t{seconds_timecode(c.start, standard)}\t"
                   f"{seconds_timecode(c.end, standard)}\t{lines[0]}")
        out += lines[1:]
    return "\n".join(out) + "\n"


def shifted(cues, offset):
    """Cues `offset` seconds earlier (a script timed against a source's own
    timecode, e.g. one starting at 01;00;00;00); what ends before 0 goes."""
    if not offset:
        return cues
    out = []
    for c in cues:
        if c.end - offset > 0:
            out.append(dataclasses.replace(c, start=max(0.0, c.start - offset),
                                           end=c.end - offset))
    return out


PARSERS = {".srt": parse_srt, ".vtt": parse_vtt, ".ass": parse_ass, ".ssa": parse_ass,
           ".txt": parse_text_script}


def _encodings(raw):
    """The encodings to try on a subtitle file: UTF-16 when it has a byte
    order mark or its every other byte is 0 (subtitle scripts are often
    saved as UTF-16), else UTF-8, Shift_JIS, Latin-1."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return ("utf-16",)
    if len(raw) >= 4:
        half = len(raw) // 2
        if raw[1::2].count(0) > half * 0.4 and not raw[0::2].count(0):
            return ("utf-16-le",)
        if raw[0::2].count(0) > half * 0.4 and not raw[1::2].count(0):
            return ("utf-16-be",)
    return ("utf-8-sig", "cp932", "latin-1")


def load_subtitles(path, standard="NTSC"):
    """Cues of a subtitle file (timecodes of a text script are the disc
    `standard`'s)."""
    ext = os.path.splitext(path)[1].lower()
    parse = PARSERS.get(ext, parse_srt)
    if ext == ".txt":
        base = os.path.dirname(os.path.abspath(path))
        parse = lambda text: parse_text_script(text, standard, base)     # noqa: E731
    with open(path, "rb") as f:
        raw = f.read()
    for enc in _encodings(raw):
        try:
            return parse(raw.decode(enc))
        except UnicodeDecodeError:
            continue
        except ValueError as e:
            raise CaptionError(f"{path}: {e}")
    raise CaptionError(f"{path}: cannot decode subtitle file")
