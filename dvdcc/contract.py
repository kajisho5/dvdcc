"""Machine-readable contract (`dvdcc contract --json`), in the shape the AI Video
Production OS registry reads (skill_id, version, contract_version, provides,
dependencies, not_provided)."""

from . import __version__

SKILL_ID = "dvdcc"
CONTRACT_VERSION = "1.1"

TOOLS = [
    {"tool_id": "dvdcc/captions", "kind": "cli", "writes_media": True, "mutates_input": True,
     "description": "Put line-21 closed captions (CEA-608, CC1) from a Scenarist .scc or subtitles (.srt, .vtt, .ass, .txt) into the GOP user data of a DVD's MPEG-2 video, without re-encoding; in place unless -o is given",
     "argv": ["<video.m2v>", "<captions>", "[-o <out.m2v>]", "[--offset <seconds|timecode>]", "[--top]"]},
    {"tool_id": "dvdcc/check", "kind": "cli", "writes_media": False, "mutates_input": False,
     "description": "Report, cue by cue, what of a subtitle file (.srt, .vtt, .ass, .txt) CEA-608 pop-on captions cannot carry as written: characters outside the caption set (such as Japanese), lines over 32 columns, more than 4 rows, vertical text; writes nothing",
     "argv": ["check", "<subtitles>", "[--json]"]},
]


def contract():
    return {
        "skill_id": SKILL_ID,
        "id": SKILL_ID,
        "version": __version__,
        "contract_version": CONTRACT_VERSION,
        "provides": [
            {"id": "dvd.closed_captions", "lifecycle": "EXPERIMENTAL", "tool_id": "dvdcc/captions"},
            {"id": "dvd.closed_captions.check", "lifecycle": "EXPERIMENTAL", "tool_id": "dvdcc/check"},
        ],
        # No Skill dependencies (ffmpeg-skill is not used).
        "dependencies": [],
        "external_tools": [],
        "not_provided": [
            "encoding the MPEG-2 video",
            "subtitles as pictures (vtskit.subtitles)",
            "PAL video (line 21 is NTSC)",
            "network access of any kind",
        ],
        "tools": TOOLS,
        "python_api": "dvdcc.captions.load, dvdcc.captions.check, dvdcc.captions.inject_file",
        "execution": {"canonical_invocation": ["dvdcc", "contract", "--json"],
                      "network": False, "shell": False},
    }
