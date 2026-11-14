# VELTRIX FOOTBALL 2.0 — Team identity crosswalk v1

## Purpose

The OpenFootball archive and live fixture providers use different source-specific team IDs. Their IDs must never be joined by numeric coincidence or loose name similarity.

## Resolution policy

1. A verified crosswalk keyed by exact source/provider team ID, competition and country is the only route to RESOLVED.
2. A unique exact normalized name match is REVIEW_REQUIRED, never automatically resolved.
3. Multiple exact name matches are AMBIGUOUS.
4. No scoped match is UNRESOLVED.
5. Competition/country mismatches fail closed.

Normalization removes diacritics and punctuation and collapses whitespace. It deliberately preserves club-name tokens such as FC, SC and United. No fuzzy edit-distance merge is used.

## Evidence requirements

Every crosswalk row requires an HTTPS evidence URI, SHA-256 hash of the exact evidence bytes, timezone-aware verification timestamp, source/provider ID, canonical ID, competition and country. Duplicate source IDs and cross-competition/country mappings are rejected.

## Current data status

The 379 OpenFootball Nigeria results retain source-prefixed team IDs. No provider-to-canonical mappings are fabricated. The identity module is ready to receive independently verified mappings when live fixture catalogues are ingested.
