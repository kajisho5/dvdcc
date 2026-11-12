# ADR-001: Report what CEA-608 cannot carry, cue by cue

Status: accepted (2026-11-12)

## Context

dvdcc sends each subtitle as a pop-on caption. A pop-on caption holds at
most 4 rows of 32 characters, and dvdcc writes the CEA-608 basic character
set (ASCII less `* \ ^ _ ` { | } ~`, with some accented letters in their
place). Subtitles made for the screen, such as the SubRip and WebVTT files
subtitle-skill writes, often go past that: lines of 40 characters or more,
Japanese text, vertical WebVTT cues.

Before this change dvdcc fitted them silently: long lines were wrapped,
rows after the fourth were cut off, and characters with no caption
character became spaces, with one total count as a note. A user could not
tell which cue was hurt, and a disc of Japanese subtitles turned into
blank captions with a single note.

## Decision

* `dvdcc.captions.check(cues)` returns one record per thing a cue cannot
  carry as written: `characters` (none in the caption set; they become
  spaces), `long_line` (over 32 columns; wrapped), `long_word` (a word over
  32 characters; cut across rows), `rows` (more than 4 rows; the rest is
  left out, and named), `vertical` (a WebVTT `vertical:` cue; sent
  across). Each record has the cue number, start, end, the kind, a
  message and the cue's text.
* `dvdcc check SUBTITLES [--json]` prints that report without a video,
  so the problem is known before authoring. It writes nothing and exits 0
  when the check ran; the report is the result.
* A caption run (`dvdcc VIDEO CAPTIONS`, `captions.from_cues`) still sends
  every cue as before, and gives the same records as notes, one per line,
  instead of one total. Nothing is left out without a note.
* Reading subtitle-skill's output: WebVTT character references (`&amp;`
  and others) are decoded, ruby readings (`<rt>`, `<rp>`) are left out of
  the text (the base is the caption), and `vertical:rl` / `vertical:lr`
  is kept on the cue so it can be reported.
* The mode stays pop-on. Roll-up (2 to 4 rows scrolling) is not offered:
  subtitles are timed as whole cues, which is what pop-on shows.
* The characters checked are the ones dvdcc sends (the basic set). The
  608 special and extended sets (such as `♪`) are reported as missing,
  since dvdcc does not write them.

## Consequences

* The contract gains a tool, `dvdcc/check`, and a capability,
  `dvd.closed_captions.check` (contract version 1.0 to 1.1). The change is
  additive: the existing tool, its arguments and its output are the same.
* The notes of a caption run are worded per cue
  (`cue 3 at 00:00:06.500: ...`); the single total note is gone.
* Japanese and other scripts outside the caption set can still be put on
  a DVD as subpictures (vtskit); closed captions cannot carry them.
