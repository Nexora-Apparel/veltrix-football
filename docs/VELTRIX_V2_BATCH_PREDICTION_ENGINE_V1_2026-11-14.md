# VELTRIX FOOTBALL 2.0 — Batch prediction engine v1

## Target fixture contract

A target fixture must have a stable provider-scoped fixture ID, competition/team IDs, timezone-aware kickoff, source provider, source ID, provider retrieval timestamp, payload SHA-256 and rights approval reference. It is eligible only when the target snapshot was retrieved by the requested prediction cutoff and kickoff is strictly later than that cutoff.

## Batch behavior

- Accepts a list of historical model observations and scheduled target fixtures.
- Sorts eligible targets by kickoff then stable fixture ID.
- Generates up to 25 forecasts per batch.
- Does not rank or filter by favourite status; underdogs are retained.
- Duplicate target IDs are excluded in full.
- Past/live targets and targets not yet known at the cutoff are skipped explicitly.
- Missing team/competition history produces no prediction.
- The model publication flag remains false, regardless of sample floor.

## Output

The report contains target count, forecast count, duplicate/invalid/not-yet-known/no-history/capacity skip counts and fixture-level probabilities with evidence counts. It is a calculation artifact only.

## Safety boundary

No scheduler, Telegram sender, database writer, website publisher, odds engine or value-bet unlock is connected. The batch engine cannot publish predictions.


## Optional recency weighting

The engine accepts an exponential half-life setting. Equal weighting remains the default; any non-default half-life must be selected through chronological walk-forward comparison using the same weighting for the model and competition baseline.
