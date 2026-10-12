import os
import tempfile
import unittest

from dvdcc import subtitles
from dvdcc.errors import CaptionError

SRT = """﻿1\r
00:00:01,000 --> 00:00:04,000\r
<i>Hello</i> there\r
second line\r
\r
2\r
00:00:03.500 --> 00:00:06,25\r
{\\an8}Overlapping cue\r
\r
3\r
00:00:07,000 --> 00:00:07,000\r
zero length is dropped\r
\r
4\r
00:01:02,5 --> 00:01:03,000\r
\r
"""


class TestSrt(unittest.TestCase):
    def test_parse(self):
        cues = subtitles.parse_srt(SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].lines, ["Hello there", "second line"])
        self.assertEqual((cues[0].start, cues[0].end), (1.0, 3.5))   # clipped to next start
        self.assertEqual(cues[1].lines, ["Overlapping cue"])
        self.assertAlmostEqual(cues[1].end, 6.25)

    def test_sorted_and_hours(self):
        cues = subtitles.parse_srt("2\n01:00:00,000 --> 01:00:02,000\nlate\n\n"
                                   "1\n00:00:00,500 --> 00:00:01,000\nearly\n")
        self.assertEqual([c.lines[0] for c in cues], ["early", "late"])
        self.assertEqual(cues[1].start, 3600.0)

    def test_bad_timing(self):
        with self.assertRaises(ValueError):
            subtitles.parse_srt("1\n00:00:01 --> soon\ntext\n")

    def test_load_shift_jis_file(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".srt", delete=False) as f:
            f.write("1\r\n00:00:01,000 --> 00:00:02,000\r\n日本語の字幕\r\n".encode("cp932"))
        self.addCleanup(os.remove, f.name)
        self.assertEqual(subtitles.load_subtitles(f.name)[0].lines, ["日本語の字幕"])

    def test_load_utf16(self):
        # (with a byte order mark, and without)
        text = "1\r\n00:00:01,000 --> 00:00:02,000\r\n日本語の字幕\r\n"
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            with tempfile.NamedTemporaryFile("wb", suffix=".srt", delete=False) as f:
                f.write(text.encode(enc))
            self.addCleanup(os.remove, f.name)
            self.assertEqual(subtitles.load_subtitles(f.name)[0].lines, ["日本語の字幕"], enc)
        with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as f:
            f.write("1 00;00;01;00 00;00;02;00 Hello\n".encode("utf-16"))
        self.addCleanup(os.remove, f.name)
        self.assertEqual(subtitles.load_subtitles(f.name)[0].lines, ["Hello"])

    def test_load_reports_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False) as f:
            f.write("1\n12:00 --> x\nbad\n")
        self.addCleanup(os.remove, f.name)
        with self.assertRaises(CaptionError):
            subtitles.load_subtitles(f.name)


class TestFormatsAndStyles(unittest.TestCase):
    def test_srt_tags_set_position_and_colour(self):
        cues = subtitles.parse_srt(SRT)
        self.assertEqual(cues[1].position, "top")                     # {\an8}
        c = subtitles.parse_srt('1\n00:00:01,000 --> 00:00:02,000\n<font color="#ffff00">Y</font>\n')
        self.assertEqual((c[0].color, c[0].lines), ("#FFFF00", ["Y"]))

    def test_vtt(self):
        cues = subtitles.parse_vtt("WEBVTT - demo\n\nNOTE a comment\n\nSTYLE\n::cue { color: red }\n\n"
                                   "intro\n00:01.000 --> 00:02.500 line:0 align:center\n<b>Top</b>\n\n"
                                   "01:00:03.000 --> 01:00:04.000\nAn hour in\n")
        self.assertEqual([(c.start, c.end, c.lines, c.position) for c in cues],
                         [(1.0, 2.5, ["Top"], "top"), (3603.0, 3604.0, ["An hour in"], None)])
        with self.assertRaises(ValueError):
            subtitles.parse_vtt("1\n00:00:01,000 --> 00:00:02,000\nnot vtt\n")

    def test_ass(self):
        ass = ("[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
               "Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment\n"
               "Style: Default,Arial,20,&H00FFFFFF,0,2\nStyle: Sign,Arial,20,&H0000FFFF,0,8\n\n"
               "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
               "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Line, with comma\\Nsecond\n"
               "Dialogue: 0,0:00:03.00,0:00:04.50,Sign,,0,0,0,,{\\c&H0000FF&}Red sign\n"
               "Comment: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,ignored\n")
        cues = subtitles.parse_ass(ass)
        self.assertEqual(cues[0].lines, ["Line, with comma", "second"])
        self.assertEqual((cues[1].position, cues[1].color), ("top", "#FF0000"))   # style + override
        self.assertEqual((cues[0].color, cues[0].style_color), (None, "#FFFFFF"))
        self.assertEqual(len(cues), 2)

class TestTextScripts(unittest.TestCase):
    """The plain subtitle script of disc authoring tools: number, start and
    end timecode, text, more lines of text."""

    EXAMPLE = ("1 00;00;02;02 00;00;03;15 The cat never came back.\n"
               "She just walked away.\n"
               "2 00;00;05;18 00;00;09;20 I hope she's all right.\n"
               "She always looked out the window with a special kind of longing.\n")

    def test_timecodes(self):
        tc = subtitles.timecode_seconds
        f = 1001 / 30000
        self.assertAlmostEqual(tc("00;00;02;02"), 62 * f)
        self.assertAlmostEqual(tc("0;0;12;3"), 363 * f)               # (no leading zeros)
        self.assertAlmostEqual(tc("00;01;00;02"), 1800 * f)          # drop frame: ;00 and ;01 skipped
        self.assertAlmostEqual(tc("00;10;00;00"), 17982 * f)         # ... but not every tenth minute
        self.assertAlmostEqual(tc("00:01:00:00"), 1800 * f)          # NTSC non drop frame
        self.assertAlmostEqual(tc("00:01:00:00", "PAL"), 60.0)
        self.assertAlmostEqual(tc("00:00:01:24", "PAL"), 1.96)
        self.assertAlmostEqual(tc("01:02:03,250"), 3723.25)           # a time, not a timecode
        for bad, std in (("00;00;01;30", "NTSC"), ("00:00:01:25", "PAL"), ("00;61;00;00", "NTSC"),
                         ("12:00", "NTSC")):
            with self.assertRaises(ValueError, msg=bad):
                tc(bad, std)

    def test_timecodes_written(self):
        f = 1001 / 30000
        for frame in (0, 1, 29, 30, 1799, 1800, 1801, 17981, 17982, 107892, 107893):
            t = frame * f
            code = subtitles.seconds_timecode(t)
            self.assertAlmostEqual(subtitles.timecode_seconds(code), t, msg=code)
        self.assertEqual(subtitles.seconds_timecode(1800 * f), "00;01;00;02")
        self.assertEqual(subtitles.seconds_timecode(107892 * f), "01;00;00;00")
        self.assertEqual(subtitles.seconds_timecode(61.96, "PAL"), "00:01:01:24")

    def test_example(self):
        cues = subtitles.parse_text_script(self.EXAMPLE)
        self.assertEqual([c.lines for c in cues],
                         [["The cat never came back.", "She just walked away."],
                          ["I hope she's all right.",
                           "She always looked out the window with a special kind of longing."]])
        f = 1001 / 30000
        self.assertAlmostEqual(cues[0].start, 62 * f)
        self.assertAlmostEqual(cues[1].end, 290 * f)
        # tabs, blank lines, a subtitle whose text starts on the next line
        cues = subtitles.parse_text_script("1\t0:0:1:0\t0:0:2:0\n\nOnly below\n", "PAL")
        self.assertEqual((cues[0].start, cues[0].end, cues[0].lines), (1.0, 2.0, ["Only below"]))

    def test_refused(self):
        for text, why in (("1 00;00;03;00 00;00;02;00 Backwards\n", "ends before it starts"),
                          ("Just some notes\n", "expected"),
                          ("\n\n", "no subtitles")):
            with self.assertRaises(ValueError) as cm:
                subtitles.parse_text_script(text)
            self.assertIn(why, str(cm.exception))

    def test_written_and_read_back(self):
        cues = subtitles.parse_text_script(self.EXAMPLE)
        again = subtitles.parse_text_script(subtitles.to_text_script(cues))
        self.assertEqual([(round(c.start, 3), round(c.end, 3), c.lines) for c in again],
                         [(round(c.start, 3), round(c.end, 3), c.lines) for c in cues])
        pal = subtitles.to_text_script([subtitles.Cue(1.0, 2.5, ["A", "B"])], "PAL")
        self.assertEqual(pal, "1\t00:00:01:00\t00:00:02:12\tA\nB\n")

    def test_loaded_with_the_standard(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "script.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("1 00:00:01:00 00:00:02:00 Hello\n")
            self.assertAlmostEqual(subtitles.load_subtitles(path, "PAL")[0].start, 1.0)
            self.assertAlmostEqual(subtitles.load_subtitles(path, "NTSC")[0].start, 1.001)

    def test_offset(self):
        cues = [subtitles.Cue(3600.5, 3602.0, ["a"]), subtitles.Cue(3599.0, 3600.2, ["b"]),
                subtitles.Cue(3590.0, 3595.0, ["gone"])]
        out = subtitles.shifted(cues, 3600.0)
        self.assertEqual([(round(c.start, 3), round(c.end, 3), c.lines) for c in out],
                         [(0.5, 2.0, ["a"]), (0.0, 0.2, ["b"])])
        self.assertIs(subtitles.shifted(cues, 0), cues)

if __name__ == "__main__":
    unittest.main()
