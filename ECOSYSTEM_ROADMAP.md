# Roadmap — dvdcc

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **納品 (Delivery)**, status `active`, optional component.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.1.1, CEA-608 captions into m2v. Python 3.11+ stdlib, unittest, CI on Ubuntu + macOS. Optional component (installed with --with-optional). oncemore vendors this library.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| DVD字幕(CEA-608) | done |  |

## Wiring

Not reachable from the agent; encodes with ffmpeg directly.

## Steps

- [x] **1. (optional) Contract in the OS schema** — skill_id, version, provides[]
  - Done when: validates against the OS schema
- [x] **2. Captions from subtitle-skill with 608 limits reported** ([#14](https://github.com/kajisho5/dvdcc/pull/14)) — read subtitle-skill SRT / VTT, apply CEA-608 limits (32 columns, rows, roll-up or pop-on) and report every cue that cannot be carried as written (characters outside 608's set such as Japanese, overlong lines) instead of dropping it. Field review 2026-11-05 (Velisa ROADMAP, third round)
  - なぜ要るか：英語のクローズドキャプション付き DVD を、字幕データから欠けなく作れる。日本語が載らないことも事前に分かる
  - Done when: a fixture with one 40-character line and one Japanese line reports both

## Boundaries

Vendored by oncemore (`oncemore/_vendor/`).

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
