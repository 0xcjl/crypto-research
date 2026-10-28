"""Append-only model judgments and deterministic 30/90 day outcome arithmetic."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from common import VERSION, asset_key, digest, instant, now, number, safe_id
from metrics import change

SIGNALS = {"BUY", "SELL", "WATCH", "UNDETERMINED", "NOT_APPLICABLE"}


def entries(runtime: Path) -> list[dict]:
    path = runtime / "judgments.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        # A truncated line is an error, not silently skipped history.
        return [json.loads(line) for line in handle if line.strip()]


@contextmanager
def locked(runtime: Path):
    path = runtime / ".ledger.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        path.unlink()


def append(runtime: Path, value: dict) -> dict:
    previous = entries(runtime)
    record = {**value, "recorded_at": now(), "previous_hash": previous[-1]["record_hash"] if previous else None}
    record["record_hash"] = digest(record)
    with (runtime / "judgments.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def audit(runtime: Path) -> dict:
    previous = None
    for row in entries(runtime):
        copy = dict(row)
        stated = copy.pop("record_hash")
        if row["previous_hash"] != previous or digest(copy) != stated:
            raise ValueError("Ledger hash chain mismatch")
        previous = stated
    return {"status": "ok", "entries": len(entries(runtime)), "head": previous,
            "note": "Hash chain detects edits; not a remote timestamp or signature."}


def check_refs(refs: list, evidence: dict):
    available = {item["evidence_id"] for item in evidence["records"] if item["status"] == "ok"}
    if not refs or any(ref not in available for ref in refs):
        raise ValueError("Each judgment/quote requires successful evidence references")


def check_quote(quote: dict, asset: dict, evidence: dict):
    if asset_key(quote["asset"]) != asset_key(asset):
        raise ValueError("Quote asset mismatch")
    if quote.get("currency") != "USD":
        raise ValueError("Review price must use USD; explicitly convert stablecoin quotes with evidence")
    if number(quote["price"]) is None or number(quote["price"]) <= 0:
        raise ValueError("Positive quote required")
    instant(quote["observed_at"])
    check_refs(quote["evidence_refs"], evidence)
    if not quote.get("venue") or not quote.get("instrument"):
        raise ValueError("Quote venue/instrument required")


def record_decision(document: dict, evidence: dict, runtime: Path) -> dict:
    value = dict(document)
    safe_id(value["decision_id"])
    if value.get("authored_by") != "model":
        raise ValueError("Analysis and signals must be authored by the model")
    if value["signal"] not in SIGNALS or value["risk"] not in {"low", "medium", "high", "critical", "unknown"}:
        raise ValueError("Invalid signal/risk enum")
    at = instant(value["as_of"])
    if at > instant(now()) + timedelta(minutes=5):
        raise ValueError("Decision timestamp is in the future")
    check_refs(value["evidence_refs"], evidence)
    if not value.get("thesis") or not value.get("recheck_conditions") or not value.get("execution_agent") or not value.get("model"):
        raise ValueError("Thesis, recheck conditions and executing agent required")
    if value.get("asset"):
        value["asset_key"] = asset_key(value["asset"])
    elif value["signal"] != "NOT_APPLICABLE":
        raise ValueError("Tradable judgments require verified asset identity")
    if value.get("reference_quote"):
        check_quote(value["reference_quote"], value["asset"], evidence)
        age = (at - instant(value["reference_quote"]["observed_at"])).total_seconds()
        if not 0 <= age <= 900:
            raise ValueError("Baseline quote must be no more than 15 min before decision")
    if value["signal"] in {"BUY", "SELL"} and not value.get("reference_quote"):
        raise ValueError("BUY/SELL requires a fresh, sourced reference price")
    if value["signal"] in {"BUY", "SELL"}:
        if not value.get("signal_window") or not value.get("invalidation_conditions") or not value.get("valid_until"):
            raise ValueError("BUY/SELL needs signal_window, valid_until and invalidation_conditions")
        if instant(value["valid_until"]) <= at:
            raise ValueError("Signal validity must end after decision time")
        if not value.get("benchmark") and not value.get("benchmark_gap"):
            raise ValueError("Missing benchmark requires an explicit reason")
    if value.get("benchmark"):
        check_quote(value["benchmark"]["reference_quote"], value["benchmark"]["asset"], evidence)
        if not 0 <= (at - instant(value["benchmark"]["reference_quote"]["observed_at"])).total_seconds() <= 900:
            raise ValueError("Benchmark baseline must align within 15 min")
    for assertion in value.get("assertions", []):
        safe_id(assertion["id"])
        if not assertion.get("condition"):
            raise ValueError("Falsifiable assertion condition required")
        check_refs(assertion["evidence_refs"], evidence)
    assertion_ids = [item["id"] for item in value.get("assertions", [])]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("Assertion IDs must be unique")
    value.update(record_type="decision", skill_version=VERSION,
                 due_at={str(day): (at + timedelta(days=day)).isoformat().replace("+00:00", "Z") for day in (30, 90)})
    with locked(runtime):
        audit(runtime)
        if any(row.get("decision_id") == value["decision_id"] and row["record_type"] == "decision" for row in entries(runtime)):
            raise ValueError("Decision already exists; append a new ID with supersedes instead")
        return append(runtime, value)


def due(runtime: Path, at: str | None = None) -> list[dict]:
    rows, current = entries(runtime), instant(at or now())
    complete = {(r["decision_id"], r["horizon_days"]) for r in rows if r["record_type"] == "review" and r["status"] == "complete"}
    return [{"decision_id": row["decision_id"], "horizon_days": day, "due_at": timestamp,
             "decision": row} for row in rows if row["record_type"] == "decision"
            for horizon, timestamp in row["due_at"].items()
            if (day := int(horizon)) and instant(timestamp) <= current and (row["decision_id"], day) not in complete]


def outcome(decision: dict, review: dict, evidence: dict) -> dict:
    day = review["horizon_days"]
    if day not in (30, 90):
        raise ValueError("Horizon must be 30 or 90 days")
    target = instant(decision["due_at"][str(day)])
    if instant(review["reviewed_at"]) < target:
        raise ValueError("Review not due yet")
    base, quote = decision.get("reference_quote"), review.get("quote")
    result = {"return_pct": None, "direction_hit": None, "excess_return_pp": None,
              "relative_direction_hit": None, "price_status": "not_evaluable",
              "relative_status": "not_evaluable" if decision.get("benchmark") else "not_applicable"}
    if quote and base:
        check_quote(quote, decision["asset"], evidence)
        if any(quote[field] != base[field] for field in ("venue", "instrument", "currency")):
            raise ValueError("Outcome venue/instrument/currency differs from frozen baseline; mark not evaluable")
        if not 0 <= (instant(quote["observed_at"]) - target).total_seconds() <= 86400:
            raise ValueError("Outcome quote must be at/after horizon and within 24h; historical bars needed if late")
        if instant(quote["observed_at"]) > instant(review["reviewed_at"]):
            raise ValueError("Outcome quote is later than review")
        result["return_pct"] = change(base["price"], quote["price"])
        result["price_status"] = "evaluable"
        if decision["signal"] in {"BUY", "SELL"}:
            result["direction_hit"] = result["return_pct"] > 0 if decision["signal"] == "BUY" else result["return_pct"] < 0
    benchmark, endpoint = decision.get("benchmark"), review.get("benchmark_quote")
    if benchmark and endpoint and result["return_pct"] is not None:
        check_quote(endpoint, benchmark["asset"], evidence)
        if any(endpoint[field] != benchmark["reference_quote"][field] for field in ("venue", "instrument", "currency")):
            raise ValueError("Outcome benchmark differs from frozen venue/instrument/currency")
        if abs((instant(endpoint["observed_at"]) - instant(quote["observed_at"])).total_seconds()) > 3600:
            raise ValueError("Outcome benchmark must align within 1h")
        if instant(endpoint["observed_at"]) > instant(review["reviewed_at"]):
            raise ValueError("Future benchmark quote")
        excess = result["return_pct"] - change(benchmark["reference_quote"]["price"], endpoint["price"])
        result["excess_return_pp"] = excess
        result["relative_status"] = "evaluable"
        if decision["signal"] in {"BUY", "SELL"}:
            result["relative_direction_hit"] = excess > 0 if decision["signal"] == "BUY" else excess < 0
    return result


def record_review(document: dict, evidence: dict, runtime: Path) -> dict:
    value = dict(document)
    if value.get("authored_by") != "model" or value.get("status") not in {"complete", "pending_data"}:
        raise ValueError("Review explanation must come from model; valid status required")
    if not value.get("assessment") or not value.get("execution_agent") or not value.get("model"):
        raise ValueError("Model assessment and executing agent required")
    if instant(value["reviewed_at"]) > instant(now()) + timedelta(minutes=5):
        raise ValueError("Review timestamp is in the future")
    with locked(runtime):
        audit(runtime)
        rows = entries(runtime)
        decision = next(r for r in rows if r["record_type"] == "decision" and r["decision_id"] == value["decision_id"])
        if any(r["record_type"] == "review" and r["decision_id"] == value["decision_id"] and r["horizon_days"] == value["horizon_days"] and r["status"] == "complete" for r in rows):
            raise ValueError("This horizon already has a completed review")
        assertions = {r["id"] for r in decision.get("assertions", [])}
        reviewed_assertions = set()
        for assertion in value.get("assertion_results", []):
            if assertion["id"] not in assertions or assertion["status"] not in {"occurred", "not_occurred", "unknown"}:
                raise ValueError("Invalid assertion review")
            if assertion["id"] in reviewed_assertions:
                raise ValueError("Duplicate assertion review")
            reviewed_assertions.add(assertion["id"])
            if assertion["status"] != "unknown":
                check_refs(assertion["evidence_refs"], evidence)
        if value["status"] == "complete" and reviewed_assertions != assertions:
            raise ValueError("Completed review must address every original assertion")
        arithmetic = outcome(decision, value, evidence)
        if value["status"] == "pending_data" or arithmetic["price_status"] != "evaluable":
            if not value.get("data_gap"):
                raise ValueError("Missing review price requires an explicit data_gap")
        if arithmetic["relative_status"] == "not_evaluable" and not value.get("benchmark_gap"):
            raise ValueError("Missing preselected benchmark result requires benchmark_gap")
        missing_expected = ((decision.get("reference_quote") and arithmetic["price_status"] != "evaluable")
                            or (decision.get("benchmark") and arithmetic["relative_status"] != "evaluable"))
        if missing_expected and value["status"] == "complete" and not value.get("final_data_unavailable_reason"):
            raise ValueError("Incomplete review must stay pending_data, or explicitly justify permanent data unavailability")
        return append(runtime, {**value, "record_type": "review", "outcome": arithmetic})


def summary(runtime: Path) -> dict:
    rows = entries(runtime)
    decisions = {r["decision_id"]: r for r in rows if r["record_type"] == "decision"}
    groups = {}
    for horizon in (30, 90):
        for signal in ("BUY", "SELL"):
            eligible = [r for r in rows if r["record_type"] == "review" and r["status"] == "complete"
                        and r["horizon_days"] == horizon and decisions[r["decision_id"]]["signal"] == signal]
            valid = [r for r in eligible if r["outcome"]["direction_hit"] is not None]
            relative = [r for r in eligible if r["outcome"]["relative_direction_hit"] is not None]
            groups[f"{horizon}d_{signal}"] = {"n": len(valid), "hits": sum(r["outcome"]["direction_hit"] for r in valid),
                "hit_rate": sum(r["outcome"]["direction_hit"] for r in valid) / len(valid) if valid else None,
                "relative_n": len(relative), "relative_hits": sum(r["outcome"]["relative_direction_hit"] for r in relative),
                "relative_not_evaluable": sum(r["outcome"]["relative_status"] == "not_evaluable" for r in eligible),
                "unique_assets": len({decisions[r["decision_id"]].get("asset_key") for r in valid}),
                "not_evaluable": len(eligible) - len(valid)}
    return {"groups": groups, "note": "Observational signal snapshots, not realized trades; excludes WATCH/unknown. Repeated signals on the same asset are correlated; report unique assets."}
