"""The command line."""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from dvdcc.__main__ import main

from .test_captions import decode, have, make_m2v


@unittest.skipUnless(have("ffmpeg"), "needs ffmpeg")
class TestCli(unittest.TestCase):
    def test_srt_to_copy(self):
        d = tempfile.mkdtemp(prefix="dvdcc-cli-")
        self.addCleanup(shutil.rmtree, d, True)
        m2v, out, srt = (os.path.join(d, n) for n in ("v.m2v", "c.m2v", "c.srt"))
        make_m2v(m2v, 4)
        with open(srt, "w") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,500\nHello\n")
        o, e = io.StringIO(), io.StringIO()
        with redirect_stdout(o), redirect_stderr(e):
            rc = main([m2v, srt, "-o", out])
        self.assertEqual(rc, 0, e.getvalue())
        self.assertIn("captions over 120 frames", o.getvalue())
        mpg = os.path.join(d, "v.mpg")
        import subprocess
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-fflags", "+genpts",
                        "-i", out, "-c", "copy", "-f", "dvd", mpg], check=True)
        self.assertEqual([c[2] for c in decode(mpg)], ["Hello"])

    def test_bad_file(self):
        e = io.StringIO()
        with redirect_stderr(e), redirect_stdout(io.StringIO()):
            rc = main(["nothing.m2v", "nothing.scc"])
        self.assertEqual(rc, 1)
        self.assertIn("dvdcc:", e.getvalue())
