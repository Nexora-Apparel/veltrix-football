# Wyscout Open Match Event Dataset Rights Review — 2026-11-12

- Dataset: Pappalardo et al. (2019), A public data set of spatio-temporal match events in soccer competitions
- Canonical source: https://figshare.com/collections/Soccer_match_event_dataset/4415000
- Data descriptor: https://www.nature.com/articles/s41597-019-0247-7
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- License text: https://creativecommons.org/licenses/by/4.0/
- Review date: 2026-11-12

## Permitted scope

The dataset's published data descriptor identifies the seven event datasets as CC BY 4.0. VELTRIX may retain the source attribution, preserve the licence and change notices, and use the historical shot-event records to train and evaluate an independent xG estimator.

Required attribution:

**Shot-event training data: Pappalardo et al. (2019), “A public data set of spatio-temporal match events in soccer competitions”, CC BY 4.0. Adapted to train the VELTRIX xG model.**

## Limits

- Historical only; not a current-season or live feed.
- It does not provide current lineups, injuries or current team statistics.
- Train VELTRIX's own xG model from raw shot locations and event context. Do not label a VELTRIX estimate as official Wyscout xG.
- Preserve original match, team, player and event identifiers as source IDs; do not assume they are canonical identities.
- Retain attribution and CC BY 4.0 notices in derived dataset documentation.

The dataset is not ingested by this Phase 2 change. It is a rights-cleared historical event source reserved for the later xG-data/model phase.
