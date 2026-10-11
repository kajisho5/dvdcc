"""Closed captions (line 21, CEA-608) on a DVD.

The caption bytes (parity, row addresses, characters), pop-on captions from
subtitles, Scenarist files, the DVD user data in the video stream, and a
built disc whose captions ffmpeg's caption decoder reads back as the text.
"""

import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from dvdcc import captions
from dvdcc.subtitles import Cue


def have(*names):
    return all(shutil.which(n) for n in names)


def decode(path):
    """The captions ffmpeg's decoder reads from a file: [(start, end, text)]."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
                          "-i", f"movie={path}[out0+subcc]", "-map", "0:1", "-f", "srt", "-"],
                         capture_output=True, text=True, check=True).stdout
    cues = []
    for block in out.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        a, b = lines[1].split(" --> ")
        sec = lambda s: sum(float(x) * k for x, k in zip(s.replace(",", ".").split(":"), (3600, 60, 1)))  # noqa: E731
        text = re.sub(r"<[^>]+>|\{[^}]*\}", "", "\n".join(lines[2:]))
        cues.append((sec(a), sec(b), text))
    return cues


class TestBytes(unittest.TestCase):
    def test_parity_and_codes(self):
        self.assertEqual(captions.parity(0x14), 0x94)      # two bits set: parity bit added
        self.assertEqual(captions.parity(0x20), 0x20)      # one bit: already odd
        self.assertEqual(captions.EOC, (0x94, 0x2F))
        self.assertEqual(captions.pac(15), (0x94, 0xE0))   # row 15, white
        self.assertEqual(captions.pac(15, 8), (0x94, 0xF4))  # ... indented 8
        self.assertEqual(captions.pac(1), (0x91, 0x40))

    def test_text(self):
        pairs, dropped = captions.text_pairs("Año *")
        # A ñ o space, then '*' (no such character) as a space, padded with a null
        self.assertEqual(pairs, [captions.pair(0x41, 0x7E), captions.pair(0x6F, 0x20),
                                 captions.pair(0x20, 0x00)])
        self.assertEqual(dropped, 1)
        self.assertEqual(captions.wrap(["a " * 20]), ["a " * 15 + "a", "a a a a"])
        self.assertEqual(len(captions.wrap(["x"] * 6)), 4)

    def test_pop_on(self):
        s, notes = captions.from_cues([Cue(1.0, 3.0, ["Hi"]), Cue(4.0, 5.0, ["Again"])])
        f = s.frames
        start, end = captions.frame_of(1.0), captions.frame_of(3.0)
        self.assertEqual((f[start], f[start + 1]), (captions.EOC, captions.EOC))
        self.assertEqual(f[end], captions.EDM)
        loaded = [k for k in f if k < start]
        self.assertEqual(f[min(loaded)], captions.RCL)       # loading starts with RCL
        sent = [b for pr in f.values() for b in pr]
        self.assertIn(captions.parity(0x48), sent)            # "H"
        self.assertIn(captions.parity(0x69), sent)            # "i"
        self.assertEqual(notes, [])
        # too much text right after the previous one: shown late, said so
        long = ["x" * 32] * 4
        s, notes = captions.from_cues([Cue(1.0, 1.1, ["a"]), Cue(1.2, 3.0, long)])
        self.assertTrue(any("late" in n for n in notes), notes)

    def test_scc(self):
        s = captions.parse_scc("Scenarist_SCC V1.0\n\n00:00:01:00\t9420 9420 94ae\n\n"
                               "00:00:01;00\t942f\n")
        f = captions.frame_of(1.0)
        # the second line's start is taken: it goes on after the first
        self.assertEqual([s.frames[k] for k in range(f, f + 4)],
                         [(0x94, 0x20), (0x94, 0x20), (0x94, 0xAE), (0x94, 0x2F)])
        with self.assertRaises(ValueError):
            captions.parse_scc("1\n00:00:01,000 --> 00:00:02,000\nnot scc\n")

    def test_user_data(self):
        d = captions.user_data([(0x94, 0x20), captions.FILLER])
        self.assertEqual(d, bytes.fromhex("000001b2434301f8" "84" "ff9420fe8080" "ff8080fe8080"))
        self.assertEqual(captions.gop_sizes(b"\0\0\1\xb8xxxx\0\0\1\0aa\0\0\1\0bb\0\0\1\xb8yyyy\0\0\1\0"),
                         [2, 1])


@unittest.skipUnless(have("ffmpeg"), "needs ffmpeg")
class TestStream(unittest.TestCase):
    def test_injected_and_decoded(self):
        d = tempfile.mkdtemp(prefix="dvdcc-")
        self.addCleanup(shutil.rmtree, d, True)
        m2v = os.path.join(d, "v.m2v")
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=size=720x480:rate=30000/1001:duration=6", "-target",
                        "ntsc-dvd", "-an", "-f", "mpeg2video", m2v], check=True)
        s, _ = captions.from_cues([Cue(1.0, 2.5, ["First one"]), Cue(3.0, 5.0, ["Two", "rows"])])
        self.assertEqual(captions.inject_file(m2v, s), 180)
        mpg = os.path.join(d, "v.mpg")
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-fflags",
                        "+genpts", "-i", m2v, "-c", "copy", "-f", "dvd", mpg], check=True)
        got = decode(mpg)
        self.assertEqual([c[2] for c in got], ["First one", "Two\nrows"])
        # (a GOP's captions are read at its start: within a GOP, 0.6 s)
        for (a, b, _), want in zip(got, ((1.0, 2.5), (3.0, 5.0))):
            self.assertLess(abs(a - want[0]), 0.7)
            self.assertLess(abs(b - want[1]), 0.7)


def make_m2v(path, seconds=6):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=720x480:rate=30000/1001:duration={seconds}", "-target",
                    "ntsc-dvd", "-an", "-f", "mpeg2video", path], check=True)


@unittest.skipUnless(have("ffmpeg", "dvdauthor"), "needs ffmpeg and dvdauthor")
class TestDisc(unittest.TestCase):
    """Captions through dvdauthor: the VOB of the authored disc decodes to the
    text, and the titleset says it has line-21 captions (field 1)."""

    def test_authored(self):
        d = tempfile.mkdtemp(prefix="dvdcc-disc-")
        self.addCleanup(shutil.rmtree, d, True)
        m2v, mpg = os.path.join(d, "v.m2v"), os.path.join(d, "v.mpg")
        make_m2v(m2v)
        scc = os.path.join(d, "c.scc")
        with open(scc, "w") as f:
            # pop-on "OK" at 2 s: RCL ENM PAC(row 15) "OK" EOC, erased at 4 s
            f.write("Scenarist_SCC V1.0\n\n00:00:01:00\t9420 9420 94ae 94ae 94e0 94e0 4fcb "
                    "942f 942f\n\n00:00:04:00\t942c 942c\n")
        schedule, _ = captions.load(scc)
        captions.inject_file(m2v, schedule)
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-fflags", "+genpts",
                        "-i", m2v, "-c", "copy", "-f", "dvd", mpg], check=True)
        xml = os.path.join(d, "dvd.xml")
        with open(xml, "w") as f:
            f.write(f'<dvdauthor dest="{d}/out"><vmgm/><titleset><titles>'
                    '<video format="ntsc" aspect="4:3" caption="field1"/>'
                    f'<pgc><vob file="{mpg}"/></pgc></titles></titleset></dvdauthor>')
        subprocess.run(["dvdauthor", "-x", xml], check=True, capture_output=True,
                       env=dict(os.environ, VIDEO_FORMAT="NTSC"))
        vts = os.path.join(d, "out", "VIDEO_TS")
        texts = [c[2] for c in decode(os.path.join(vts, "VTS_01_1.VOB"))]
        self.assertIn("OK", texts)
        with open(os.path.join(vts, "VTS_01_0.IFO"), "rb") as f:
            ifo = f.read()
        self.assertTrue(ifo[0x201] & 0x80)


if __name__ == "__main__":
    unittest.main()
