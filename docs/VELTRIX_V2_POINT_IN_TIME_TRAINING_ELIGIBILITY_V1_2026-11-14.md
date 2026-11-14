# VELTRIX FOOTBALL 2.0 — Point-in-time training eligibility v1

## Two distinct use cases

The model prediction function and the historical walk-forward evaluator have different evidence requirements.

### Future forecast

A settled result can inform a future forecast when:
- the match event is safely before the target cutoff;
- the source availability basis is at or before the cutoff;
- the exact local retrieval/recorded timestamp is at or before the cutoff;
- source identity and score are valid.

This allows the engine to learn from free provider data retrieved today for forecasts made after retrieval, without pretending the provider's historical publication time is known.

### Historical walk-forward evaluation

Training observations must additionally have point_in_time_certifiable=true. This prevents records with only a conservative availability proxy or a late one-time retrieval from being silently used to reconstruct past knowledge.

The evaluator reports the number of non-certifiable input observations and excludes them from every model and baseline training fold. Target outcomes may still be scored once they are known by evaluation_as_of; target-result availability is not a training feature.

## 5DollarFootballAPI

The existing parser uses the explicit conservative basis provider_finished_status_conservative_4d and carries point_in_time_certifiable=false. The model adapter preserves that flag and the original retrieval timestamp. These records can inform forecasts after retrieval but cannot enter historical walk-forward training until the source provides stronger point-in-time evidence.

## OpenFootball World

The immutable source-file commit timestamp and actual import timestamp are preserved. Date-only kickoff remains null; a two-calendar-day UTC safety boundary is enforced. These observations can train future forecasts after the boundary. They are never used as walk-forward target fixtures because they lack exact kickoff timestamps.
