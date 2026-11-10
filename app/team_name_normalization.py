"""Canonical football team-name normalization shared by provider and fixture identity code.

This module contains identity normalization only; it has no prediction,
probability, feature-engineering or model dependencies.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_team_name(name: Any) -> str:
    """Normalize provider wrappers and explicit, reviewed club aliases.

    Ambiguous fuzzy matches are not performed here. Women's and reserve-team
    markers remain distinct so similarly named squads are never conflated.
    """
    raw_name = str(name or "").strip().casefold()
    explicit_reserve = bool(re.search(r"(?:\(\s*(?:r|b)\s*\)|\s+(?:r|b))$", raw_name))
    explicit_women = bool(re.search(r"(?:\(\s*w\s*\)|\s+w)$", raw_name))
    normalized = unicodedata.normalize("NFKD", raw_name)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace("ø", "o").replace("ł", "l").replace("đ", "d").replace("ð", "d").replace("þ", "th")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    edge_markers = {"fc", "afc", "cf", "sc", "ac", "as", "ec", "sbv", "acf", "cd", "ud", "bc"}
    while tokens and tokens[0] in edge_markers:
        tokens.pop(0)
    while tokens and tokens[-1] in edge_markers:
        tokens.pop()
    key = "".join(tokens)
    if explicit_reserve:
        key += "reservemarker"
    if explicit_women:
        key += "womenmarker"
    aliases = {
        "manutd": "manchesterunited",
        "manunited": "manchesterunited",
        "manchesterutd": "manchesterunited",
        "mancity": "manchestercity",
        "manchestercty": "manchestercity",
        "spurs": "tottenhamhotspur",
        "tottenham": "tottenhamhotspur",
        "wolves": "wolverhamptonwanderers",
        "wolverhampton": "wolverhamptonwanderers",
        "psg": "parissaintgermain",
        "parissg": "parissaintgermain",
        "barca": "barcelona",
        "bayern": "bayernmunich",
        "bayernmunchen": "bayernmunich",
        "juve": "juventus",
        "atleticomadrid": "atleticodemadrid",
        "athleticomadrid": "atleticodemadrid",
        "athmadrid": "atleticodemadrid",
        "newcastleutd": "newcastleunited",
        "newcastle": "newcastleunited",
        "deportivolacoruna": "deportivocoruna",
        "deportivoacoruna": "deportivocoruna",
        "caosasuna": "osasuna",
        "westham": "westhamunited",
        "westhamutd": "westhamunited",
        "athleticclub": "athleticbilbao",
        "athbilbao": "athleticbilbao",
        "internazionale": "intermilan",
        "internazionalemilano": "intermilan",
        "inter": "intermilan",
        "psveindhoven": "psv",
        "feyenoordrotterdam": "feyenoord",
        "nec": "necnijmegen",
        "argentinosjrs": "argentinosjuniors",
        "independrivadavia": "independienterivadavia",
        "losclille": "lille",
        "lilleosc": "lille",
        "rclens": "lens",
    }
    return aliases.get(key, key)
