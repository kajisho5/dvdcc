<p><img src="docs/images/logo/lockup-dark.svg" alt="dvdcc" height="56"></p>

# dvdcc

Put **line-21 closed captions** (CEA-608, CC1) into the MPEG-2 video of a
**DVD**, without re-encoding it. Pure Python, no dependencies.

* **From a Scenarist (.scc) file:** the byte pairs caption tools write are
  used as they are, from the frame of their timecode.
* **From subtitles** (SubRip, WebVTT, ASS / SSA, text scripts; UTF-8, UTF-16
  or Shift_JIS): each is sent as a pop-on caption.
  * It is loaded into the hidden memory before its time, shown at its start,
    and erased at its end.
  * Long lines are wrapped to 32 columns and 4 rows.
  * A caption with too much text to load in time is shown late, with a note.
* **Into the video:** the captions go into the stream as the DVD's GOP user
  data (`00 00 01 B2 'C' 'C' 01 F8`), one word pair per frame. This is the
  data a DVD player sends to line 21.

日本語の説明は [README.ja.md](README.ja.md) にあります。

## Why

Plenty of tools read DVD captions back, but very few put them in. ffmpeg
cannot embed .scc files. The open caption libraries that write CEA-608
target H.264 and HEVC (A/53 SEI), not the DVD's MPEG-2 user data.

## Install

```sh
pip install dvdcc
```

A release is made by the version: when the version in `pyproject.toml`
(and `dvdcc/__init__.py`) reaches `main` without a tag of its own,
`.github/workflows/release.yml` runs the tests, builds the package, makes
the GitHub release with its tag and publishes to PyPI (trusted publishing,
environment `pypi`). Merging the version bump is all it takes.

## Use

```sh
dvdcc video.m2v captions.scc              # in place
dvdcc video.m2v subs.srt -o captioned.m2v --offset 01;00;00;00
```

```python
from dvdcc import captions

schedule, notes = captions.load("subs.srt")      # or a .scc
frames = captions.inject_file("video.m2v", schedule)
```

Then mux and author the disc as usual. Tell the authoring tool that the
titleset has line-21 captions, so players that look find them. With
dvdauthor, that is `<video ... caption="field1"/>`.

**Limits:**

* NTSC only, since line 21 belongs to the 525-line picture.
* 29.97 frames per second. Film with soft 3:2 pulldown counts its fields
  differently, so it is not supported.
* Field 1 (CC1) only.

## Tests

```sh
python -m unittest discover -s tests -t .
```

The tests cover:

* the caption bytes: parity, preamble address codes, the character set;
* pop-on timing and Scenarist parsing;
* the user data layout;
* with ffmpeg, captions put into a test video that **ffmpeg's own caption
  decoder** (lavfi `subcc`) reads back as the text at the right times;
* with dvdauthor as well, a whole authored disc whose VOB decodes to the
  captions and whose IFO marks line-21 captions.

dvdcc was first written for [oncemore](https://github.com/kajisho5/oncemore),
a DVD and Blu-ray authoring app.

## Support

dvdcc is free and stays free. If it saves you time, you can support its
development through [GitHub Sponsors](https://github.com/sponsors/kajisho5)
(the **Sponsor** button at the top of this repository). Bug reports help just
as much: [Issues](https://github.com/kajisho5/dvdcc/issues).

The logo, colours and writing rules: [docs/DESIGN.md](docs/DESIGN.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
