"""Conservative parsing for the JAMS-style labels emitted by the detector."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Tuple


PITCH_CLASSES = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_ROOT_TOKEN = re.compile(r"^([A-Ga-g])([#♯b♭x]{0,2})$")
_NO_CHORD = {"N", "X", "NONE", "NOCHORD", "NO-CHORD", "NO_CHORD"}
_EXTENDED_QUALITY = re.compile(r"^(?:maj|major|M|min|minor|m)?6/9$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedChord:
    original_label: str
    root: str
    root_pitch_class: int
    quality: str
    bass: Optional[str] = None
    bass_pitch_class: Optional[int] = None
    bass_degree: Optional[str] = None


def _root_info(token: str) -> Optional[Tuple[str, int]]:
    token = token.strip().replace("♯", "#").replace("♭", "b")
    match = _ROOT_TOKEN.match(token)
    if not match:
        return None

    letter = match.group(1).upper()
    accidental = match.group(2)
    pitch_class = PITCH_CLASSES[letter]
    for mark in accidental:
        pitch_class += 2 if mark == "x" else 1 if mark == "#" else -1
    return f"{letter}{accidental}", pitch_class % 12


def _canonical_quality(value: str) -> str:
    """Return the small canonical vocabulary used by patterns.json."""

    value = value.strip().replace("♯", "#").replace("♭", "b")
    value = value.replace(" ", "").replace("(", "").replace(")", "")
    if value in {"", "M", "Maj", "Major"}:
        return "maj"
    if value in {"m", "Min", "Minor"}:
        return "min"

    lower = value.lower()
    # Handle case-insensitive long spellings before the one-letter M/m forms.
    # This keeps MAJ7 and MIN7 from being mistaken for those one-letter forms.
    if lower in {"major", "maj"}:
        return "maj"
    if lower in {"minor", "min"}:
        return "min"
    if lower.startswith("major") and len(lower) > 5:
        return f"maj{lower[5:]}"
    if lower.startswith("maj") and len(lower) > 3:
        return f"maj{lower[3:]}"
    if lower.startswith("minor") and len(lower) > 5:
        return f"min{lower[5:]}"
    if lower.startswith("min") and len(lower) > 3:
        return f"min{lower[3:]}"

    # M7/M9 and m7/m9 are common compact spellings. Their case carries the
    # major/minor distinction, while the canonical quality vocabulary does not.
    if value.startswith("M") and len(value) > 1:
        return f"maj{value[1:].lower()}"
    if value.startswith("m") and len(value) > 1:
        return f"min{value[1:].lower()}"

    if lower.startswith("dominant"):
        return lower[8:] or "7"
    if lower.startswith("dom"):
        return lower[3:] or "7"

    aliases = {
        "major-triad": "maj",
        "minor-triad": "min",
    }
    return aliases.get(lower, lower)


def _is_scale_degree(value: str) -> bool:
    return bool(re.match(r"^(?:[#b]?\d+)$", value.strip(), re.IGNORECASE))


def _canonical_scale_degree(value: str) -> str:
    """Normalize a detector's scale-degree bass token for Roman-numeral output."""

    return value.strip().replace("♯", "#").replace("♭", "b").lower()


def _is_extended_quality(value: str) -> bool:
    return bool(_EXTENDED_QUALITY.match(value.replace(" ", "")))


def _relative_bass_degree(root_pitch_class: int, bass_pitch_class: int) -> Optional[str]:
    """Express a note-name bass as a compact chromatic scale degree."""

    degrees = {
        0: "1",
        1: "b2",
        2: "2",
        3: "b3",
        4: "3",
        5: "4",
        6: "#4",
        7: "5",
        8: "b6",
        9: "6",
        10: "b7",
        11: "7",
    }
    return degrees.get((bass_pitch_class - root_pitch_class) % 12)


def _split_quality_and_bass(value: str) -> Tuple[str, Optional[str]]:
    """Split slash-bass notation without mistaking maj6/9 for an inversion."""

    value = value.strip()
    if "/" not in value:
        return value, None

    # Extended quality spellings such as maj6/9 are quality, not bass notes.
    if _is_extended_quality(value):
        return value, None

    quality, possible_bass = value.rsplit("/", 1)
    if _root_info(possible_bass) is not None:
        return quality, possible_bass
    # Detector labels may encode a scale-degree inversion as /3 or /b3.
    if _is_scale_degree(possible_bass):
        return quality, None
    return value, None


def parse_chord_label(label: str) -> Optional[ParsedChord]:
    """Parse a detector label, returning None for excluded/non-chord labels.

    Roots are normalized to pitch classes, so C# and Db compare as enharmonic
    equivalents. The original label is retained for display by the caller.
    """

    if not isinstance(label, str):
        return None
    original = label
    stripped = label.strip()
    if not stripped or stripped.upper().replace(" ", "") in _NO_CHORD:
        return None

    if ":" in stripped:
        root_token, raw_quality = stripped.split(":", 1)
    else:
        root_token, raw_quality = stripped, ""

    bass_token: Optional[str] = None
    bass_degree: Optional[str] = None
    if ":" not in stripped and "/" in root_token:
        root_token, bass_token = root_token.split("/", 1)
        if _root_info(bass_token) is None:
            if not _is_scale_degree(bass_token):
                return None
            bass_degree = _canonical_scale_degree(bass_token)
            bass_token = None
    else:
        original_quality = raw_quality
        raw_quality, bass_token = _split_quality_and_bass(raw_quality)
        # _split_quality_and_bass deliberately leaves scale-degree basses out
        # of the note-name result. Preserve them separately for display while
        # continuing to ignore them for harmonic matching.
        compact_quality = original_quality.replace(" ", "")
        if not _is_extended_quality(compact_quality):
            possible_degree = compact_quality.rsplit("/", 1)[-1] if "/" in compact_quality else ""
            if _is_scale_degree(possible_degree):
                bass_degree = _canonical_scale_degree(possible_degree)

    root = _root_info(root_token)
    if root is None:
        return None
    bass = _root_info(bass_token) if bass_token else None
    if bass_token and bass is None:
        return None

    root_name, root_pitch_class = root
    bass_name = bass[0] if bass else None
    bass_pitch_class = bass[1] if bass else None
    if bass_degree is None and bass_pitch_class is not None:
        bass_degree = _relative_bass_degree(root_pitch_class, bass_pitch_class)
    if bass_degree == "1":
        bass_degree = None
    return ParsedChord(
        original_label=original,
        root=root_name,
        root_pitch_class=root_pitch_class,
        quality=_canonical_quality(raw_quality),
        bass=bass_name,
        bass_pitch_class=bass_pitch_class,
        bass_degree=bass_degree,
    )


def canonical_quality_set(values: Iterable[str]) -> set[str]:
    if isinstance(values, str):
        values = [values]
    return {_canonical_quality(value) for value in values}


def quality_is_allowed(chord: ParsedChord, quality_values: Iterable[str]) -> bool:
    """Check a parsed chord against one editable quality set."""

    return chord.quality in canonical_quality_set(quality_values)


def quality_display_suffix(chord: ParsedChord) -> str:
    """Return the quality detail that should follow a Roman numeral.

    Roman-numeral case already communicates a major/minor triad. Keep
    ``maj`` on major-seventh/major-extension chords so ``7`` remains
    distinguishable from a dominant seventh, while omitting the redundant
    ``min`` prefix from lowercase minor numerals.
    """

    if chord.quality in {"", "maj", "min"}:
        return ""
    if chord.quality.startswith("min"):
        return chord.quality[3:]
    return chord.quality


def format_roman_numeral(base_numeral: str, chord: ParsedChord) -> str:
    """Decorate a pattern's Roman degree with detected quality and bass."""

    result = base_numeral.strip() + quality_display_suffix(chord)
    if chord.bass_degree:
        result += f"/{chord.bass_degree}"
    return result


__all__ = [
    "ParsedChord",
    "canonical_quality_set",
    "format_roman_numeral",
    "parse_chord_label",
    "quality_display_suffix",
    "quality_is_allowed",
]
