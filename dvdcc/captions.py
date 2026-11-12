"""Closed captions (line 21, CEA-608) on a DVD.

A DVD carries line-21 captions in its MPEG-2 video: user data after every
GOP header, "CC", then one caption word pair per frame of the GOP (in
display order) for each field. A caption decoder in the player or TV turns
them back into text. They come from

* a Scenarist (.scc) file: CEA-608 byte pairs with the timecode they start
  at, as caption tools write them, used as they are; or
* subtitles (SubRip, WebVTT, ...): each one sent as a "pop-on" caption: the
  text is loaded into the hidden memory before its time, shown at its start
  (end of caption) and erased at its end.

A pop-on caption is at most 4 rows of 32 characters from the CEA-608 basic
set (ASCII less a few, plus some accented letters). What a subtitle has
beyond that cannot be carried as written: `check` reports it cue by cue
(characters with no caption character, such as Japanese, become spaces;
longer lines are wrapped; rows past the fourth are left out), and the
caption is still sent, so nothing is dropped without a word.

Captions are NTSC only (line 21 of a 525-line picture), on 29.97 fps
video, field 1 (CC1).
"""

import mmap
import os
import re

from . import subtitles
from .errors import CaptionError

FPS = 30000 / 1001
COLUMNS = 32
ROWS = 4                       # rows of a pop-on caption (dvdcc's, and the usual)
FILLER = (0x80, 0x80)          # no data (two nulls with odd parity)

# preamble address code, first and second byte base, for rows 1..15
_PAC_ROWS = {1: (0x11, 0x40), 2: (0x11, 0x60), 3: (0x12, 0x40), 4: (0x12, 0x60),
             5: (0x15, 0x40), 6: (0x15, 0x60), 7: (0x16, 0x40), 8: (0x16, 0x60),
             9: (0x17, 0x40), 10: (0x17, 0x60), 11: (0x10, 0x40), 12: (0x13, 0x40),
             13: (0x13, 0x60), 14: (0x14, 0x40), 15: (0x14, 0x60)}
# the basic character set is ASCII but for these
_SPECIAL = {"á": 0x2A, "é": 0x5C, "í": 0x5E, "ó": 0x5F, "ú": 0x60, "ç": 0x7B, "÷": 0x7C,
            "Ñ": 0x7D, "ñ": 0x7E, "█": 0x7F}
_NOT_BASIC = set("*\\^_`{|}~")


def parity(b):
    """The byte with its odd-parity bit (bit 7)."""
    b &= 0x7F
    return b | 0x80 if bin(b).count("1") % 2 == 0 else b


def pair(a, b):
    return parity(a), parity(b)


# CC1 control codes (first byte 0x14, field 1, data channel 1), with parity
RCL, EDM, ENM, EOC = (pair(0x14, x) for x in (0x20, 0x2C, 0x2E, 0x2F))


def pac(row, column=0):
    """Preamble address code: row 1..15, white, indented to `column` (a
    multiple of 4; the rest is padding with spaces)."""
    first, base = _PAC_ROWS[row]
    return pair(first, base + 0x10 + (column // 4) * 2 if column >= 4 else base)


def text_pairs(text):
    """Characters of one caption row as byte pairs; what the basic set has
    no character for becomes a space. Returns (pairs, characters dropped)."""
    codes, dropped = [], 0
    for ch in text:
        if ch in _SPECIAL:
            codes.append(_SPECIAL[ch])
        elif has_character(ch):
            codes.append(ord(ch))
        else:
            codes.append(0x20)
            dropped += 1
    if len(codes) % 2:
        codes.append(0x00)
    return [pair(a, b) for a, b in zip(codes[0::2], codes[1::2])], dropped


def has_character(ch):
    """Whether the CEA-608 basic set (as dvdcc sends it) has `ch`."""
    return ch in _SPECIAL or (" " <= ch <= "~" and ch not in _NOT_BASIC)


def wrap(lines, rows_max=ROWS):
    """Caption rows of at most 32 characters (words wrapped), at most
    `rows_max` (None: all of them)."""
    rows = []
    for line in lines:
        words, cur = line.split(), ""
        for w in words:
            while len(w) > COLUMNS:
                if cur:
                    rows.append(cur)
                    cur = ""
                rows.append(w[:COLUMNS])
                w = w[COLUMNS:]
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= COLUMNS:
                cur += " " + w
            else:
                rows.append(cur)
                cur = w
        if cur:
            rows.append(cur)
    return rows if rows_max is None else rows[:rows_max]


def frame_of(t):
    return int(round(t * FPS))


class Schedule:
    """Caption word pairs per frame (field 1)."""

    def __init__(self):
        self.frames = {}

    def free(self, f):
        return f not in self.frames

    def put(self, f, p):
        self.frames[f] = p

    def put_from(self, f, pairs):
        """Put pairs on the free frames from `f` on; returns the last frame used."""
        last = f
        for p in pairs:
            while not self.free(f):
                f += 1
            self.put(f, p)
            last, f = f, f + 1
        return last

    def pairs(self, count):
        return [self.frames.get(f, FILLER) for f in range(count)]


def _clock(t):
    h, rest = divmod(round(t * 1000), 3_600_000)
    m, rest = divmod(rest, 60_000)
    return f"{h:02d}:{m:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


def check(cues):
    """What of each cue a pop-on caption cannot carry as written, as a list
    of dicts: cue (its number, from 1), start, end, kind ("characters",
    "long_line", "long_word", "rows", "vertical"), message, and the cue's
    text. Nothing is reported for a cue that fits."""
    problems = []
    for n, c in enumerate(cues, 1):
        if c.image:
            continue

        def say(kind, message):
            problems.append({"cue": n, "start": round(c.start, 3), "end": round(c.end, 3),
                             "kind": kind, "message": f"cue {n} at {_clock(c.start)}: {message}",
                             "text": "\n".join(c.lines)})

        text = "".join(c.lines)
        missing = [ch for ch in text if not ch.isspace() and not has_character(ch)]
        if missing:
            shown = "".join(dict.fromkeys(missing))
            more = "..." if len(shown) > 10 else ""
            say("characters", f"{len(missing)} character(s) have no closed-caption character "
                f"and become spaces: {shown[:10]}{more}")
        for k, line in enumerate(c.lines, 1):
            width = len(" ".join(line.split()))
            if width > COLUMNS:
                rows = len(wrap([line], None))
                say("long_line", f"line {k} is {width} characters, a caption row holds "
                    f"{COLUMNS}: wrapped onto {rows} rows")
            for w in line.split():
                if len(w) > COLUMNS:
                    say("long_word", f"\"{w[:20]}...\" is {len(w)} characters without a "
                        f"space: cut across rows")
        rows = wrap(c.lines, None)
        if len(rows) > ROWS:
            lost = " ".join(rows[ROWS:])
            say("rows", f"needs {len(rows)} rows, a pop-on caption shows {ROWS}: "
                f"\"{lost[:40]}{'...' if len(lost) > 40 else ''}\" is left out")
        if getattr(c, "vertical", False):
            say("vertical", "is written vertically; captions run across: sent horizontally")
    return problems


def from_cues(cues, position="bottom"):
    """A Schedule from subtitles: one pop-on caption each. Returns
    (schedule, notes): one note for each thing `check` finds (what a caption
    cannot carry as written) and for each caption shown late."""
    s = Schedule()
    notes = [p["message"] for p in check(cues)]
    shown_until = -1            # the frame the last caption was shown at (its EOC)
    last_end = None
    for n, c in enumerate(cues, 1):
        rows = wrap(c.lines)
        if not rows:
            continue
        load = [RCL, RCL, ENM, ENM]
        top = (c.position or position) == "top"
        first_row = 2 if top else 16 - len(rows)
        for k, row in enumerate(rows):
            col = (COLUMNS - len(row)) // 2
            p = pac(first_row + k, col)
            chars, _ = text_pairs(" " * (col % 4) + row)
            load += [p, p] + chars
        start, end = frame_of(c.start), frame_of(c.end)
        # load into the hidden memory after the previous caption went up
        # (its EOC swaps the memories), ending just before this one's start
        first = max(shown_until + 2, start - len(load) - 2)
        loaded = s.put_from(first, load)
        show = max(start, loaded + 1)
        if show > start + 2:
            notes.append(f"cue {n} at {_clock(c.start)}: shown {(show - start) / FPS:.2f}s late "
                         "(too much text since the previous one)")
        if last_end is not None and last_end < show:
            s.put_from(last_end, [EDM, EDM])       # the previous one goes at its end
        shown_until = s.put_from(show, [EOC, EOC])
        last_end = max(end, shown_until + 1)
    if last_end is not None:
        s.put_from(last_end, [EDM, EDM])
    return s, notes


_SCC_LINE = re.compile(r"^(\d{1,2}[:;]\d{2}[:;]\d{2}[:;.]\d{2})\s+((?:[0-9a-fA-F]{4}\s*)+)$")


def parse_scc(text):
    """A Scenarist caption file -> Schedule (its byte pairs as they are,
    from the frame of their timecode on)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("Scenarist_SCC"):
        raise ValueError("not a Scenarist caption file (no Scenarist_SCC header)")
    s = Schedule()
    for n, line in enumerate(lines[1:], 2):
        m = _SCC_LINE.match(line)
        if not m:
            raise ValueError(f"line {n}: expected a timecode and byte pairs")
        tc = m[1].replace(".", ";")
        try:
            f = frame_of(subtitles.timecode_seconds(tc, "NTSC"))
        except ValueError as e:
            raise ValueError(f"line {n}: {e}")
        words = m[2].split()
        s.put_from(f, [(int(w[:2], 16), int(w[2:], 16)) for w in words])
    return s


def load(path, offset=0.0, position="bottom", standard="NTSC"):
    """Captions of a file: .scc as they are, anything else as subtitles.
    `offset` (seconds) is taken off every time. Returns (schedule, notes)."""
    if path.lower().endswith(".scc"):
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            try:
                s = parse_scc(f.read())
            except ValueError as e:
                raise CaptionError(f"{path}: {e}")
        if offset:
            shift = frame_of(offset)
            s.frames = {f - shift: p for f, p in s.frames.items() if f >= shift}
        return s, []
    cues = subtitles.shifted(subtitles.load_subtitles(path, standard), offset)
    return from_cues(cues, position)


# -- the MPEG-2 video stream ------------------------------------------------------

def gop_sizes(b):
    """Pictures in each GOP of an MPEG-2 elementary stream, in order."""
    sizes, i = [], 0
    while True:
        i = b.find(b"\x00\x00\x01", i)
        if i < 0 or i + 4 > len(b):
            break
        code = b[i + 3]
        if code == 0xB8:
            sizes.append(0)
        elif code == 0x00 and sizes:
            sizes[-1] += 1
        i += 4
    return sizes


def user_data(pairs):
    """The DVD caption user data for a GOP: its frames' word pairs (field 1,
    with field 2 empty), odd field first."""
    n = len(pairs)
    if n > 31:
        raise ValueError("a GOP of more than 31 pictures cannot carry DVD captions")
    out = bytearray(b"\x00\x00\x01\xb2CC\x01\xf8")
    out.append(0x80 | (n << 1))
    for a, b in pairs:
        out += bytes([0xFF, a, b, 0xFE, 0x80, 0x80])
    return bytes(out)


def inject_file(path, schedule):
    """Write the captions into an MPEG-2 elementary stream (in place): after
    each GOP header, the user data for that GOP's frames. Returns the number
    of frames."""
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            sizes = gop_sizes(mm)
            frames = schedule.pairs(sum(sizes))
            tmp = path + ".cc"
            with open(tmp, "wb") as out:
                pos = i = 0
                k = frame = 0
                while True:
                    i = mm.find(b"\x00\x00\x01\xb8", i)
                    if i < 0:
                        break
                    head = i + 8                  # start code and the 4 header bytes
                    out.write(mm[pos:head])
                    out.write(user_data(frames[frame:frame + sizes[k]]))
                    frame += sizes[k]
                    k += 1
                    pos = i = head
                out.write(mm[pos:])
        finally:
            mm.close()
    os.replace(tmp, path)
    return frame
