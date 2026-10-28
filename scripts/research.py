#!/usr/bin/env python3
"""Crypto research data CLI. All investment interpretation belongs to the host model."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

from common import VERSION, ensure_runtime, now, read_json, safe_id, write_json
from collect import collect, configure_transport, import_native, prepare, request, transport_settings
from ledger import audit, due, record_decision, record_review, summary
from metrics import calculate


def doctor(network: bool) -> dict:
    proxy, hosts = transport_settings()
    result = {"status": "local_ready", "skill_version": VERSION, "python": platform.python_version(),
              "python_supported": sys.version_info >= (3, 10), "skill_path": str(Path(__file__).resolve().parents[1]),
              "optional_credentials_configured": {key: bool(os.environ.get(key)) for key in
                   ("COINGECKO_DEMO_API_KEY", "BRAVE_SEARCH_API_KEY")},
              "native_x": "Must test host x tools; subscription is not an API credential; no cookies read by scripts.",
              "transport": {"trusted_proxy_ip": proxy, "trusted_public_hosts": sorted(hosts)}, "network": {}}
    if network:
        for name, url in {"dexscreener": "https://api.dexscreener.com/latest/dex/search?q=ethereum",
                          "binance_public_data": "https://data-api.binance.vision/api/v3/time"}.items():
            try:
                payload, _ = request(url)
                json.loads(payload)
                result["network"][name] = {"status": "ok", "checked_at": now()}
            except Exception as exc:
                result["network"][name] = {"status": "unavailable", "error_type": type(exc).__name__,
                                         "reason": str(exc) if isinstance(exc, ValueError) else "Network/provider request failed", "checked_at": now()}
        result["status"] = "network_ready" if all(row["status"] == "ok" for row in result["network"].values()) else "degraded"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor")
    p.add_argument("--network", action="store_true")
    p.add_argument("--runtime", help="Read this runtime's explicitly configured platform transport.json")
    for name in ("collect", "prepare", "metrics", "record", "due", "review", "stats", "audit"):
        p = sub.add_parser(name)
        p.add_argument("--runtime", required=True, help="Data directory outside installed skill")
        if name in {"collect", "prepare"}:
            p.add_argument("--run-id", required=True)
            p.add_argument("--full", action="store_true", help="Print full evidence; default prints only index and file paths")
        if name == "collect":
            p.add_argument("--plan", required=True)
        if name == "prepare":
            p.add_argument("--native", help="Actual captured host search/X evidence JSON")
        if name in {"metrics", "record", "review"}:
            p.add_argument("--input", required=True)
        if name in {"record", "review"}:
            p.add_argument("--evidence", required=True)
        if name == "due":
            p.add_argument("--at", help="Audit/testing only; normal scheduled runs omit this")
    args = parser.parse_args()
    if args.command == "doctor":
        if args.runtime:
            configure_transport(ensure_runtime(args.runtime))
        result = doctor(args.network)
    else:
        root = ensure_runtime(args.runtime)
        configure_transport(root)
        if args.command == "collect":
            run = root / "runs" / safe_id(args.run_id)
            if (run / "collection.json").exists():
                raise ValueError("Run already exists; use a new run-id")
            plan = read_json(args.plan)
            write_json(run / "plan.json", plan, exclusive=True)
            result = collect(plan, root)
            write_json(run / "collection.json", result, exclusive=True)
            if not args.full:
                result = {"collection_path": str(run / "collection.json"), "requests_planned": result["requests_planned"],
                          "cache_hits": result["cache_hits"], "gaps": result["gaps"],
                          "records": [{k: row.get(k) for k in ("evidence_id", "kind", "status", "url", "raw_path")}
                                      for row in result["records"]]}
        elif args.command == "prepare":
            run = root / "runs" / safe_id(args.run_id)
            native = import_native(read_json(args.native)) if args.native else None
            result = prepare(read_json(run / "collection.json"), native)
            write_json(run / "evidence.json", result, exclusive=True)
            if not args.full:
                result = {"evidence_path": str(run / "evidence.json"), "gaps": result.get("gaps", []),
                          "records": [{k: row.get(k) for k in ("evidence_id", "kind", "status", "duplicate_of", "raw_path")}
                                      for row in result["records"]]}
        elif args.command == "metrics":
            document = read_json(args.input)
            result = {"created_at": now(), "operation": document["operation"],
                      "evidence_refs": document.get("evidence_refs", []), "result": calculate(document)}
            write_json(root / "calculations" / (Path(args.input).stem + "-" + now().replace(":", "") + ".json"), result, exclusive=True)
        elif args.command == "record":
            result = record_decision(read_json(args.input), read_json(args.evidence), root)
        elif args.command == "review":
            result = record_review(read_json(args.input), read_json(args.evidence), root)
        elif args.command == "due":
            audit(root)
            result = {"due": due(root, args.at)}
        elif args.command == "stats":
            audit(root)
            result = summary(root)
        else:
            result = audit(root)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "doctor" and result["status"] == "degraded":
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, StopIteration, FileExistsError, FileNotFoundError) as exc:
        print(json.dumps({"status": "error", "error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
