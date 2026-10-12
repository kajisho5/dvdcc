"""dvdcc: line-21 closed captions (CEA-608, CC1) for DVD-Video.

Captions come from a Scenarist (.scc) file, used as it is, or from subtitles
(SubRip, WebVTT, ASS / SSA, text scripts) sent as pop-on captions, and go
into an MPEG-2 video elementary stream as the DVD's GOP user data ("CC"),
in place, without re-encoding. Author the disc with the titleset marked as
having line-21 captions (dvdauthor: <video caption="field1"/>).
"""

__version__ = "0.1.1"
