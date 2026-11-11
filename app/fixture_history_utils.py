"""Shared fixture/history identity utilities, independent of any prediction model."""
from __future__ import annotations

import re
from typing import Any

from app.team_name_normalization import normalize_team_name

LEAGUE_DIVISION_BY_CODE = {
    "PL": "E0", "ELC": "E1", "EL1": "E2", "EL2": "E3",
    "PD": "SP1", "SD": "SP2", "SA": "I1", "SB": "I2",
    "BL1": "D1", "BL2": "D2", "FL1": "F1", "FL2": "F2",
    "DED": "N1", "PPL": "P1", "SPL": "SC0", "BSA": "BRA",
    "ARG": "ARG", "BRA": "BRA", "CHN": "CHN", "JAP": "JAP",
    "USA": "USA", "MEX": "MEX", "DEN": "DEN", "NOR": "NOR",
    "SWE": "SWE", "AUT": "AUT", "FIN": "FIN", "IRL": "IRL",
    "POL": "POL", "ROM": "ROM", "RUS": "RUS", "SUI": "SUI",
}
LEAGUE_DIVISION_BY_ID = {
    39: "E0", 40: "E1", 41: "E2", 42: "E3", 43: "EC",
    140: "SP1", 141: "SP2", 135: "I1", 136: "I2",
    78: "D1", 79: "D2", 61: "F1", 62: "F2", 88: "N1",
    94: "P1", 179: "SC0", 180: "SC1", 183: "SC2", 184: "SC3",
    144: "B1", 203: "T1", 197: "G1", 128: "ARG", 71: "BRA",
    169: "CHN", 98: "JAP", 253: "USA", 262: "MEX", 119: "DEN",
    103: "NOR", 113: "SWE", 218: "AUT", 244: "FIN", 357: "IRL",
    106: "POL", 283: "ROM", 235: "RUS", 207: "SUI",
}


def _name_key(name: Any) -> str:
    """Normalize a provider team label without applying model-specific logic."""
    return normalize_team_name(name)


def _team_variant_signature(key: str) -> tuple[str, ...]:
    """Retain women's, youth, age-group and reserve markers during identity checks."""
    markers: list[str] = []
    for label, pattern in (
        ("women", r"(?:women|womens|ladies|feminin|femenino|feminino|womenmarker)$"),
        ("youth", r"(?:youth|academy|junior|juniors)$"),
        ("age_group", r"u(?:1[0-9]|2[0-3])$"),
        ("reserve", r"(?:reserves|reserve|bteam|ii|iii|iv|2|3|b|reservemarker)$"),
    ):
        if re.search(pattern, key):
            markers.append(label)
    age = re.search(r"u(1[0-9]|2[0-3])$", key)
    if age:
        markers.append("u" + age.group(1))
    reserve = re.search(r"(?:reserves|reserve|bteam|ii|iii|iv|2|3|b|reservemarker)$", key)
    if reserve:
        markers.append("r" if reserve.group(0) == "reservemarker" else reserve.group(0))
    return tuple(markers)


def _one_edit_apart(left: str, right: str) -> bool:
    """Allow one obvious spelling typo, never a broad similarity merge."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = sum(a != b for a, b in zip(left, right))
        if differences == 1:
            return True
        for index in range(len(left) - 1):
            if (
                left[index] == right[index + 1]
                and left[index + 1] == right[index]
                and left[:index] == right[:index]
                and left[index + 2:] == right[index + 2:]
            ):
                return True
        return False
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    if longer[1:] == shorter:
        return False
    i = j = edits = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            edits += 1
            j += 1
            if edits > 1:
                return False
    return True
