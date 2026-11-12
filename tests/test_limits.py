"""What CEA-608 pop-on captions cannot carry as written, reported cue by cue
(captions.check, `dvdcc check`, and the notes of a caption run), on
subtitle files laid out the way subtitle-skill writes them."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

from dvdcc import captions, subtitles
from dvdcc.__main__ import main
from dvdcc.subtitles import Cue

HERE = os.path.dirname(os.path.abspath(__file__))
SRT = os.path.join(HERE, "fixtures", "subtitle_skill.srt")
VTT = os.path.join(HERE, "fixtures", "subtitle_skill.vtt")


class TestFixture(unittest.TestCase):
    """The roadmap's case: one 40-character line and one Japanese line."""

    def test_both_reported(self):
        for path in (SRT, VTT):
            cues = subtitles.load_subtitles(path)
            self.assertEqual(len(cues), 4, path)
            problems = captions.check(cues)
            self.assertEqual([(p["cue"], p["kind"]) for p in problems],
                             [(2, "long_line"), (3, "characters")], path)
            self.assertIn("40 characters", problems[0]["message"])
            self.assertIn("wrapped onto 2 rows", problems[0]["message"])
            self.assertIn("日本語の字幕です", problems[1]["message"])
            self.assertEqual(problems[1]["text"], "日本語の字幕です")
            self.assertEqual((problems[1]["start"], problems[1]["end"]), (6.5, 9.0))

    def test_vtt_text_unescaped(self):
        cues = subtitles.load_subtitles(VTT)
        self.assertEqual(cues[3].lines, ["Ann: Fish & chips"])

    def test_cli_report(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["check", SRT]), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("cue 2 at 00:00:03.500: line 1 is 40 characters", lines[0])
        self.assertIn("cue 3 at 00:00:06.500: 8 character(s)", lines[1])
        self.assertTrue(lines[2].endswith("2 of 4 cue(s) cannot be carried as written"))

    def test_cli_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["check", VTT, "--json"]), 0)
        r = json.loads(out.getvalue())
        self.assertEqual((r["cues"], r["cues_not_as_written"]), (4, 2))
        self.assertEqual(r["limits"], {"columns": 32, "rows": 4, "mode": "pop-on"})
        self.assertEqual([p["kind"] for p in r["problems"]], ["long_line", "characters"])

    def test_cli_scc_and_missing(self):
        for name in ("x.scc", "nothing.srt"):
            e = io.StringIO()
            with redirect_stderr(e), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["check", name]), 1)
            self.assertTrue(e.getvalue().startswith("dvdcc: "), e.getvalue())

    def test_notes_of_a_caption_run(self):
        # the run sends every cue and says the same things as notes
        s, notes = captions.from_cues(subtitles.load_subtitles(SRT))
        self.assertEqual(len(notes), 2, notes)
        self.assertTrue(notes[0].startswith("cue 2 at 00:00:03.500"))
        self.assertTrue(notes[1].startswith("cue 3 at 00:00:06.500"))
        eocs = [f for f, p in s.frames.items() if p == captions.EOC]
        self.assertEqual(len(eocs), 4 * 2)     # all four shown (EOC sent twice each)


class TestLimits(unittest.TestCase):
    def test_fits(self):
        self.assertEqual(captions.check([Cue(1, 2, ["Año", "x" * 32]),
                                         Cue(3, 4, ["a " * 16])]), [])

    def test_rows_left_out(self):
        p = captions.check([Cue(1, 2, ["one", "two", "three", "four", "five", "six"])])
        self.assertEqual([x["kind"] for x in p], ["rows"])
        self.assertIn("needs 6 rows", p[0]["message"])
        self.assertIn('"five six" is left out', p[0]["message"])

    def test_long_word(self):
        p = captions.check([Cue(1, 2, ["y" * 40])])
        self.assertEqual([x["kind"] for x in p], ["long_line", "long_word"])

    def test_characters_outside_the_set(self):
        p = captions.check([Cue(1, 2, ["50% off * now ♪"])])
        self.assertEqual([x["kind"] for x in p], ["characters"])
        self.assertIn("2 character(s)", p[0]["message"])
        self.assertTrue(p[0]["message"].endswith(": *♪"))

    def test_vertical_and_ruby(self):
        cues = subtitles.parse_vtt("WEBVTT\n\nc1\n00:00:01.000 --> 00:00:02.000 vertical:rl\n"
                                   "<ruby>漢字<rt>かんじ</rt></ruby>\n\n"
                                   "c2\n00:00:03.000 --> 00:00:04.000\n"
                                   "<ruby>Tokyo<rp>(</rp><rt>TOH-kyoh</rt><rp>)</rp></ruby>\n")
        self.assertEqual([c.lines for c in cues], [["漢字"], ["Tokyo"]])
        self.assertTrue(cues[0].vertical)
        self.assertFalse(cues[1].vertical)
        self.assertEqual([x["kind"] for x in captions.check(cues)], ["characters", "vertical"])


if __name__ == "__main__":
    unittest.main()
