"""Raw-row recomputation for VELTRIX value certification.

The input contract is intentionally stricter than existing aggregate reports.
A passing statistical audit is still not a release authorization: rights,
source authenticity and signed provenance must be verified independently.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app.certification_evidence import verify_evidence_manifest, EvidenceIntegrityError

MARKETS = ("1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5")
OUTCOMES = {
    "1X2": ("home", "draw", "away"),
    "BTTS": ("yes", "no"),
    "OVER_UNDER_1_5": ("over", "under"),
    "OVER_UNDER_2_5": ("over", "under"),
    "OVER_UNDER_3_5": ("over", "under"),
}


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _rows(payload: Any, role: str) -> list[dict[str, Any]]:
    values = payload if isinstance(payload, list) else payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise EvidenceIntegrityError(f"{role} must be a JSON array or an object containing rows[].")
    return values


def _load_role(root: Path, verified: list[dict[str, Any]], role: str) -> Any:
    item = next(row for row in verified if row["role"] == role)
    return json.loads((root / item["path"]).read_text(encoding="utf-8"))


def _settled_outcome(market: str, settlement: Mapping[str, Any]) -> str:
    home, away = settlement.get("home_goals"), settlement.get("away_goals")
    if not isinstance(home, int) or isinstance(home, bool) or home < 0:
        raise EvidenceIntegrityError("Settlement home_goals must be a non-negative integer.")
    if not isinstance(away, int) or isinstance(away, bool) or away < 0:
        raise EvidenceIntegrityError("Settlement away_goals must be a non-negative integer.")
    if market == "1X2":
        return "home" if home > away else "away" if home < away else "draw"
    if market == "BTTS":
        return "yes" if home > 0 and away > 0 else "no"
    line = float(market.removeprefix("OVER_UNDER_").replace("_", "."))
    return "over" if home + away > line else "under"


def _contains_secret_key(value: Any) -> bool:
    forbidden = {"authorization", "api_key", "api-key", "apikey", "access_token", "token", "password", "secret", "credential", "key"}
    if isinstance(value, dict):
        return any(str(key).casefold() in forbidden or _contains_secret_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _request_fingerprint(descriptor: Any) -> str:
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("method"), str) or not isinstance(descriptor.get("endpoint"), str):
        raise EvidenceIntegrityError("Source request descriptor must include method and endpoint.")
    if "?" in descriptor["endpoint"] or "#" in descriptor["endpoint"]:
        raise EvidenceIntegrityError("Source request endpoint must exclude query strings and fragments.")
    if _contains_secret_key(descriptor):
        raise EvidenceIntegrityError("Source request descriptor must not contain credentials or secret fields.")
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _json_pointer(document: Any, pointer: Any) -> Any:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise EvidenceIntegrityError("Source record pointer must be an RFC 6901 JSON pointer.")
    value = document
    if not pointer:
        return value
    for raw_part in pointer[1:].split("/"):
        if "~" in raw_part.replace("~0", "").replace("~1", ""):
            raise EvidenceIntegrityError("Source record pointer contains an invalid RFC 6901 escape.")
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise EvidenceIntegrityError("Source record pointer does not resolve in retained response bytes.")
    return value


def _source_field(record: Mapping[str, Any], field: str) -> Any:
    field_map = record.get("source_field_map") or {}
    if not isinstance(field_map, dict):
        raise EvidenceIntegrityError("source_field_map must be an object when provided.")
    return field_map.get(field, field)


def _assert_source_fields(record: Mapping[str, Any], response_record: Mapping[str, Any],
                          fields: tuple[str, ...], *, timestamps: tuple[str, ...] = (),
                          numbers: tuple[str, ...] = ()) -> None:
    source = _json_pointer(response_record["_body_json"], record.get("source_pointer"))
    if not isinstance(source, dict):
        raise EvidenceIntegrityError("Source pointer must resolve to a JSON object.")
    for field in fields:
        source_key = _source_field(record, field)
        if not isinstance(source_key, str) or source_key not in source:
            raise EvidenceIntegrityError(f"Raw source response does not contain mapped field {field}.")
        actual, expected = source[source_key], record.get(field)
        if field in timestamps:
            if _time(actual) != _time(expected):
                raise EvidenceIntegrityError(f"Raw source timestamp does not match normalized field {field}.")
        elif field in numbers:
            left, right = _number(actual), _number(expected)
            if left is None or right is None or abs(left - right) > 1e-9:
                raise EvidenceIntegrityError(f"Raw source numeric value does not match normalized field {field}.")
        elif str(actual) != str(expected):
            raise EvidenceIntegrityError(f"Raw source value does not match normalized field {field}.")


def _score(rows: list[dict[str, Any]], market: str, probability_key: str) -> dict[str, Any]:
    outcomes = OUTCOMES[market]
    selected = [row for row in rows if row.get("market") == market]
    if not selected:
        return {"matches": 0, "brier_score": None, "log_loss": None}
    brier = loss = 0.0
    for row in selected:
        probs = row.get(probability_key)
        actual = row.get("outcome")
        if actual not in outcomes:
            raise EvidenceIntegrityError(f"Invalid outcome in {market} walk-forward row.")
        if probability_key == "bookmaker_odds":
            if not isinstance(probs, dict) or set(outcomes) - set(probs):
                raise EvidenceIntegrityError(f"Raw bookmaker odds are incomplete in {market} walk-forward row.")
            prices = {key: _number(probs.get(key)) for key in outcomes}
            if any(value is None or value <= 1.0 for value in prices.values()):
                raise EvidenceIntegrityError(f"Invalid raw bookmaker odds in {market} walk-forward row.")
            inverse = {key: 1.0 / float(value) for key, value in prices.items()}
            total = sum(inverse.values())
            values = {key: value / total for key, value in inverse.items()}
        else:
            if not isinstance(probs, dict) or set(outcomes) - set(probs):
                raise EvidenceIntegrityError(f"Invalid {probability_key} in {market} walk-forward row.")
            values = {key: _number(probs.get(key)) for key in outcomes}
        if any(value is None or value < 0 or value > 1 for value in values.values()):
            raise EvidenceIntegrityError(f"Invalid probability in {market} walk-forward row.")
        if abs(sum(values.values()) - 1.0) > 1e-6:
            raise EvidenceIntegrityError(f"Probabilities do not sum to one in {market} walk-forward row.")
        brier += sum((values[key] - float(key == actual)) ** 2 for key in outcomes)
        loss -= math.log(max(1e-15, values[actual]))
    return {"matches": len(selected), "brier_score": brier / len(selected), "log_loss": loss / len(selected)}


def _cluster_lower_bound(rows: list[dict[str, Any]], iterations: int = 4000) -> float | None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["kickoff"][:10]].append(row)
    dates = sorted(groups)
    if len(dates) < 2:
        return None
    rng = random.Random(20261112)
    samples: list[float] = []
    for _ in range(iterations):
        chosen = [dates[rng.randrange(len(dates))] for _ in dates]
        stake = sum(float(item["stake"]) for day in chosen for item in groups[day])
        profit = sum(float(item["profit"]) for day in chosen for item in groups[day])
        if stake > 0:
            samples.append(profit / stake)
    samples.sort()
    return samples[math.floor(0.025 * (len(samples) - 1))] if samples else None


def recompute_raw_certification(manifest_path: str | Path, *, min_walk_forward: int = 1000,
                                min_prospective: int = 300, min_dates: int = 90,
                                min_odds_coverage: float = 0.98) -> dict[str, Any]:
    """Recompute metrics from fixture-level rows; never trusts supplied summaries."""
    integrity = verify_evidence_manifest(manifest_path)
    root = Path(manifest_path).resolve(strict=True).parent
    verified = integrity["verified_artifacts"]
    data = {role: _load_role(root, verified, role) for role in (
        "walk_forward_rows", "coverage_audit", "prospective_ledger",
        "odds_snapshots", "settlement_records", "source_responses", "model_manifest",
    )}
    walk = _rows(data["walk_forward_rows"], "walk_forward_rows")
    paper = _rows(data["prospective_ledger"], "prospective_ledger")
    odds = _rows(data["odds_snapshots"], "odds_snapshots")
    settlements = _rows(data["settlement_records"], "settlement_records")
    source_responses = _rows(data["source_responses"], "source_responses")
    model_manifest = data["model_manifest"]
    if not isinstance(model_manifest, dict) or not model_manifest.get("model_version"):
        raise EvidenceIntegrityError("model_manifest must identify an immutable model_version.")
    code_commit = model_manifest.get("code_commit")
    if not isinstance(code_commit, str) or len(code_commit) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in code_commit.lower()):
        raise EvidenceIntegrityError("model_manifest must pin a full immutable Git commit SHA.")
    training_cutoff = _time(model_manifest.get("training_data_cutoff"))
    if not training_cutoff or not model_manifest.get("feature_schema_version"):
        raise EvidenceIntegrityError("model_manifest must pin timezone-aware training cutoff and feature schema version.")
    if not isinstance(data["coverage_audit"], dict):
        raise EvidenceIntegrityError("coverage_audit must be a structured object.")
    if data["coverage_audit"].get("rights_status") != "APPROVED_FOR_INTENDED_USE" or data["coverage_audit"].get("commercial_use_eligible") is not True:
        raise EvidenceIntegrityError("coverage_audit does not prove approved rights for intended commercial use.")
    approved_sources = data["coverage_audit"].get("approved_source_ids")
    if not isinstance(approved_sources, list) or not approved_sources or any(not isinstance(item, str) or not item for item in approved_sources):
        raise EvidenceIntegrityError("coverage_audit must enumerate approved source IDs.")
    approved_sources = set(approved_sources)
    calibration_versions = model_manifest.get("calibration_versions", [])
    if not isinstance(calibration_versions, list):
        raise EvidenceIntegrityError("model_manifest calibration_versions must be a list.")

    response_by_id: dict[str, dict[str, Any]] = {}
    for response in source_responses:
        response_id = str(response.get("response_id") or "").strip()
        source_id = response.get("source_id")
        fetched_at = _time(response.get("fetched_at"))
        request_fingerprint = response.get("request_fingerprint")
        request_descriptor = response.get("request_descriptor")
        expected_hash = response.get("response_sha256")
        encoded_body = response.get("body_base64")
        if not response_id or response_id in response_by_id:
            raise EvidenceIntegrityError("Source response IDs must be present and unique.")
        if source_id not in approved_sources or not fetched_at:
            raise EvidenceIntegrityError("Source response lacks rights-approved source ID or fetch timestamp.")
        if response.get("http_status") != 200:
            raise EvidenceIntegrityError("Only successful HTTP 200 source responses are certifiable.")
        for label, digest in (("request fingerprint", request_fingerprint), ("response SHA-256", expected_hash)):
            if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise EvidenceIntegrityError(f"Source response {label} is malformed.")
        if _request_fingerprint(request_descriptor) != request_fingerprint:
            raise EvidenceIntegrityError("Source request fingerprint does not match canonical redacted request metadata.")
        if not isinstance(encoded_body, str) or not encoded_body:
            raise EvidenceIntegrityError("Source response body must be retained as base64 bytes.")
        try:
            body = base64.b64decode(encoded_body, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise EvidenceIntegrityError("Source response body is not valid base64.") from exc
        if hashlib.sha256(body).hexdigest() != expected_hash:
            raise EvidenceIntegrityError("Source response body SHA-256 mismatch.")
        try:
            body_json = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceIntegrityError("Source response body must be valid UTF-8 JSON.") from exc
        response_by_id[response_id] = {**response, "_fetched_at": fetched_at, "_body_json": body_json}

    settlement_by_id: dict[str, dict[str, Any]] = {}
    for result in settlements:
        settlement_id = str(result.get("settlement_id") or "").strip()
        if not settlement_id or settlement_id in settlement_by_id:
            raise EvidenceIntegrityError("Settlement IDs must be present and unique.")
        if not result.get("source_id") or result.get("source_id") not in approved_sources or not _time(result.get("settled_at")):
            raise EvidenceIntegrityError("Settlement record lacks rights-approved source provenance or timestamp.")
        response = response_by_id.get(str(result.get("source_response_id") or ""))
        if not response or response.get("source_id") != result.get("source_id"):
            raise EvidenceIntegrityError("Settlement record is not bound to its exact source response.")
        if response["_fetched_at"] < _time(result.get("settled_at")):
            raise EvidenceIntegrityError("Settlement source response predates the recorded settlement.")
        try:
            _assert_source_fields(
                result, response,
                ("fixture_id", "status", "home_goals", "away_goals", "settled_at", "settlement_version"),
                timestamps=("settled_at",), numbers=("home_goals", "away_goals"),
            )
        except EvidenceIntegrityError as exc:
            raise EvidenceIntegrityError("Settlement source response mismatch: " + str(exc)) from exc
        if result.get("status") not in {"FT", "AET", "PEN"} or not result.get("settlement_version"):
            raise EvidenceIntegrityError("Settlement record must identify a final status and immutable settlement version.")
        if not str(result.get("fixture_id") or "").strip():
            raise EvidenceIntegrityError("Settlement record must identify a fixture.")
        _settled_outcome("1X2", result)  # Validate both source score fields once.
        settlement_by_id[settlement_id] = result

    failures: dict[str, list[str]] = {market: [] for market in MARKETS}
    walk_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_walk: set[tuple[str, str, str]] = set()
    for row in walk:
        market = row.get("market")
        if market not in MARKETS:
            raise EvidenceIntegrityError("Walk-forward evidence contains an unsupported market.")
        fixture = str(row.get("fixture_id") or "").strip()
        kickoff, predicted = _time(row.get("kickoff")), _time(row.get("prediction_at"))
        features = row.get("features")
        if not fixture or not kickoff or not predicted or not isinstance(features, list) or not features:
            failures[market].append("walk-forward row missing fixture, prediction timestamp or raw feature observations")
            continue
        feature_times = [_time(feature.get("observed_at")) for feature in features if isinstance(feature, dict)]
        feature_sources = [feature.get("source_id") for feature in features if isinstance(feature, dict)]
        feature_names = [feature.get("name") for feature in features if isinstance(feature, dict)]
        if len(feature_times) != len(features) or any(value is None for value in feature_times):
            failures[market].append("walk-forward feature observation timestamps are incomplete")
            continue
        if any(not isinstance(source, str) or source not in approved_sources for source in feature_sources):
            failures[market].append("walk-forward feature source is not rights-approved")
            continue
        if predicted >= kickoff or any(value > predicted for value in feature_times):
            failures[market].append("walk-forward feature leakage or prediction after kickoff")
            continue
        feature_response_invalid = False
        for feature in features:
            response = response_by_id.get(str(feature.get("source_response_id") or ""))
            observed = _time(feature.get("observed_at"))
            if (
                not response or response.get("source_id") != feature.get("source_id")
                or not observed or observed > response["_fetched_at"] or response["_fetched_at"] > predicted
            ):
                feature_response_invalid = True
                break
            try:
                raw_feature_value = _json_pointer(response["_body_json"], feature.get("source_pointer"))
            except EvidenceIntegrityError:
                feature_response_invalid = True
                break
            if raw_feature_value != feature.get("value"):
                feature_response_invalid = True
                break
        if feature_response_invalid:
            failures[market].append("walk-forward feature is not bound to a point-in-time source response")
            continue
        if any(not isinstance(name, str) or not name for name in feature_names) or len(set(feature_names)) != len(feature_names):
            failures[market].append("walk-forward feature names are missing or duplicated")
            continue
        if row.get("model_version") != model_manifest.get("model_version") or row.get("model_commit") != code_commit:
            failures[market].append("walk-forward model version or code commit mismatch")
            continue
        if training_cutoff >= predicted:
            failures[market].append("model training cutoff is not strictly before prediction time")
            continue
        if row.get("feature_schema_version") != model_manifest.get("feature_schema_version"):
            failures[market].append("walk-forward feature schema version mismatch")
            continue
        if market != "1X2" and (not row.get("calibration_version") or row.get("calibration_version") not in calibration_versions):
            failures[market].append("walk-forward calibration version is missing or not in model manifest")
            continue
        settlement = settlement_by_id.get(str(row.get("settlement_id") or ""))
        if not settlement or str(settlement.get("fixture_id")) != fixture:
            failures[market].append("walk-forward outcome does not join to its exact source settlement")
            continue
        if _time(settlement.get("settled_at")) <= kickoff:
            failures[market].append("walk-forward settlement timestamp is not after kickoff")
            continue
        if row.get("outcome") != _settled_outcome(market, settlement):
            failures[market].append("walk-forward outcome disagrees with source settlement score")
            continue
        key = (fixture, market, str(row.get("split") or "full"))
        if key in seen_walk:
            failures[market].append("duplicate fixture-market walk-forward row")
            continue
        seen_walk.add(key)
        if row.get("split") not in {"full", "recent_holdout"}:
            failures[market].append("walk-forward split must be full or recent_holdout")
            continue
        walk_by_market[market].append(row)

    odds_by_id: dict[str, dict[str, Any]] = {}
    for quote in odds:
        quote_id = str(quote.get("snapshot_id") or "").strip()
        if quote.get("market") not in MARKETS:
            raise EvidenceIntegrityError("Odds evidence contains an unsupported market.")
        if not quote_id or quote_id in odds_by_id:
            raise EvidenceIntegrityError("Odds snapshot IDs must be present and unique.")
        odds_by_id[quote_id] = quote

    paper_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_paper: set[tuple[str, str]] = set()
    for row in paper:
        market = row.get("market")
        if market not in MARKETS:
            raise EvidenceIntegrityError("Prospective ledger contains an unsupported market.")
        fixture = str(row.get("fixture_id") or "").strip()
        key = (fixture, market)
        if not fixture or key in seen_paper:
            failures[market].append("missing fixture ID or duplicate fixture-market prospective selection")
            continue
        seen_paper.add(key)
        kickoff = _time(row.get("kickoff"))
        fetched = _time(row.get("odds_fetched_at"))
        quote_time = _time(row.get("quote_updated_at"))
        if not kickoff or not fetched or not quote_time or not (quote_time <= fetched < kickoff):
            failures[market].append("prospective odds are missing, stale-order invalid, or post-kickoff")
            continue
        if (kickoff - quote_time).total_seconds() > 24 * 3600:
            failures[market].append("prospective bookmaker quote exceeds 24-hour maximum age")
            continue
        quote = odds_by_id.get(str(row.get("odds_snapshot_id") or ""))
        if not quote or str(quote.get("fixture_id")) != fixture or quote.get("market") != market:
            failures[market].append("prospective row does not join to its exact odds snapshot")
            continue
        if quote.get("source_id") not in approved_sources:
            failures[market].append("odds snapshot source is not rights-approved")
            continue
        quote_response = response_by_id.get(str(quote.get("source_response_id") or ""))
        if (
            not quote_response or quote_response.get("source_id") != quote.get("source_id")
            or quote_response["_fetched_at"] != _time(quote.get("observed_at"))
        ):
            failures[market].append("odds snapshot is not bound to its exact source response")
            continue
        try:
            _assert_source_fields(
                quote, quote_response,
                ("fixture_id", "market", "bookmaker", "kickoff", "decimal_odds", "observed_at", "quote_updated_at"),
                timestamps=("kickoff", "observed_at", "quote_updated_at"), numbers=("decimal_odds",),
            )
        except EvidenceIntegrityError as exc:
            failures[market].append("odds snapshot source response mismatch: " + str(exc))
            continue
        if _time(quote.get("observed_at")) != fetched or _time(quote.get("quote_updated_at")) != quote_time:
            failures[market].append("odds snapshot timestamps do not match prospective row")
            continue
        if _time(quote.get("kickoff")) != kickoff or quote.get("bookmaker") != row.get("bookmaker"):
            failures[market].append("odds snapshot kickoff or bookmaker does not match prospective row")
            continue
        settlement = settlement_by_id.get(str(row.get("settlement_id") or ""))
        if not settlement or str(settlement.get("fixture_id")) != fixture:
            failures[market].append("prospective row does not join to its exact settlement")
            continue
        if settlement.get("source_id") not in approved_sources:
            failures[market].append("settlement source is not rights-approved")
            continue
        if row.get("model_commit") != code_commit:
            failures[market].append("prospective model commit provenance mismatch")
            continue
        if _time(settlement.get("settled_at")) <= kickoff:
            failures[market].append("settlement timestamp is not after kickoff")
            continue
        settled_outcome = _settled_outcome(market, settlement)
        if row.get("outcome") != settled_outcome:
            failures[market].append("prospective outcome disagrees with source settlement score")
            continue
        if row.get("model_version") != model_manifest.get("model_version") or row.get("model_commit") != code_commit:
            failures[market].append("prospective model version or code commit mismatch")
            continue
        if market != "1X2" and row.get("calibration_version") not in calibration_versions:
            failures[market].append("prospective calibration version is missing or not in model manifest")
            continue
        stake, price = _number(row.get("stake")), _number(row.get("decimal_odds"))
        if stake is None or stake <= 0 or price is None or price <= 1:
            failures[market].append("invalid stake or decimal odds")
            continue
        won = row.get("won")
        if not isinstance(won, bool):
            failures[market].append("prospective settlement requires boolean won")
            continue
        selection = str(row.get("selection") or "").casefold()
        outcome = str(row.get("outcome") or "").casefold()
        if selection not in OUTCOMES[market] or outcome != settled_outcome or won != (selection == settled_outcome):
            failures[market].append("selection result does not agree with source settlement outcome")
            continue
        snapshot_price = _number(quote.get("decimal_odds"))
        if snapshot_price is None or abs(snapshot_price - price) > 1e-6:
            failures[market].append("prospective odds do not match the exact snapshot price")
            continue
        fee = _number(row.get("fees"))
        if fee is None or fee < 0:
            failures[market].append("explicit non-negative fees are required")
            continue
        profit = stake * (price - 1.0) - fee if won else -stake - fee
        if _number(row.get("recorded_profit")) is None or abs(float(row["recorded_profit"]) - profit) > 1e-6:
            failures[market].append("recorded net profit does not match stake, price, result and fees")
            continue
        paper_by_market[market].append({**row, "stake": stake, "profit": profit, "kickoff": kickoff.isoformat()})

    market_results: dict[str, Any] = {}
    for market in MARKETS:
        full = [row for row in walk_by_market[market] if row.get("split") == "full"]
        holdout = [row for row in walk_by_market[market] if row.get("split") == "recent_holdout"]
        # Count unique fixture IDs; duplicate split rows cannot inflate the sample.
        full_ids = {str(row["fixture_id"]) for row in full}
        if len(full_ids) < min_walk_forward:
            failures[market].append("insufficient unique walk-forward fixtures")
        model_metrics = _score(full, market, "model_probabilities")
        holdout_model_metrics = _score(holdout, market, "model_probabilities")
        benchmark_metrics: dict[str, Any] = {}
        if model_metrics["matches"] < min_walk_forward:
            failures[market].append("walk-forward probability rows are incomplete")
        if market == "1X2":
            for scope, scope_rows in (("full", full), ("recent_holdout", holdout)):
                model_scope = _score(scope_rows, market, "model_probabilities")
                market_scope = _score(scope_rows, market, "bookmaker_odds")
                benchmark_metrics[scope] = {"model": model_scope, "bookmaker": market_scope}
                if not scope_rows or model_scope["matches"] != market_scope["matches"]:
                    failures[market].append(f"{scope} bookmaker comparison does not use identical fixtures")
                elif model_scope["brier_score"] >= market_scope["brier_score"] or model_scope["log_loss"] >= market_scope["log_loss"]:
                    failures[market].append(f"{scope} 1X2 model does not beat de-vigged bookmaker Brier and log loss")
        selections = paper_by_market[market]
        dates = {row["kickoff"][:10] for row in selections}
        stake = sum(row["stake"] for row in selections)
        profit = sum(row["profit"] for row in selections)
        roi = profit / stake if stake else None
        lower = _cluster_lower_bound(selections)
        quote_coverage = len(selections) / len([row for row in paper if row.get("market") == market]) if any(row.get("market") == market for row in paper) else 0.0
        if len(selections) < min_prospective:
            failures[market].append("insufficient source-joined prospective settled selections")
        if len(dates) < min_dates:
            failures[market].append("insufficient distinct prospective match dates")
        if quote_coverage < min_odds_coverage:
            failures[market].append("timestamped odds coverage below required threshold")
        if roi is None or roi <= 0:
            failures[market].append("recomputed prospective net ROI is not positive")
        if lower is None or lower <= 0:
            failures[market].append("date-clustered 95% ROI lower confidence bound is not positive")
        market_results[market] = {
            "walk_forward_unique_fixtures": len(full_ids),
            "walk_forward_metrics": model_metrics,
            "recent_holdout_metrics": holdout_model_metrics,
            "bookmaker_comparisons": benchmark_metrics,
            "prospective_joined_selections": len(selections),
            "distinct_match_dates": len(dates),
            "timestamped_odds_coverage": quote_coverage,
            "net_roi": roi,
            "date_clustered_roi_lower_95": lower,
            "failures": failures[market],
            "diagnostic_pass": not failures[market],
        }

    return {
        "integrity_status": integrity["integrity_status"],
        "statistical_status": "RAW_EVIDENCE_THRESHOLDS_MET" if all(not rows for rows in failures.values()) else "RAW_EVIDENCE_INCOMPLETE",
        "release_authorized": False,
        "markets": market_results,
        "blocking_note": "Raw statistical recomputation is not source authenticity, licensing approval or signed attestation. Runtime release remains disabled.",
    }
