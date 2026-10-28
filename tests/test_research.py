"""Behavioral regression coverage for evidence, math, immutable judgments and review windows."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import asset_key, ensure_runtime, instant, number
from collect import collect, compact_data, configure_transport, fetch_one, import_native, prepare, public_url, resolve_source
from ledger import audit, due, outcome, record_decision, record_review, summary
from metrics import candles, change, concentration, delta, depth
from research import doctor

ASSET = {"chain": "ethereum", "native_id": "eth"}
BTC = {"chain": "bitcoin", "native_id": "btc"}
EVIDENCE = {"records": [{"evidence_id": "p1", "status": "ok", "url": "https://example.com/price"}]}


def quote(price=100, at="2026-01-01T00:00:00Z", asset=None):
    return {"asset": asset or ASSET, "price": price, "currency": "USD", "observed_at": at,
            "venue": "fixture", "instrument": "BTCUSD" if asset == BTC else "ETHUSD", "evidence_refs": ["p1"]}


def decision(signal="BUY"):
    return {"decision_id": "eth-20260101", "authored_by": "model", "execution_agent": "test-model-fixture",
            "model": "fixture-only", "as_of": "2026-01-01T00:00:00Z", "asset": ASSET,
            "signal": signal, "risk": "high", "thesis": "Fixture, not a real investment judgment",
            "signal_window": "1 week", "valid_until": "2026-01-08T00:00:00Z", "invalidation_conditions": ["fixture invalidation"],
            "recheck_conditions": ["Fixture event"], "evidence_refs": ["p1"], "reference_quote": quote(),
            "assertions": [{"id": "event1", "condition": "Fixture event by horizon", "evidence_refs": ["p1"]}],
            "benchmark": {"asset": BTC, "reference_quote": quote(100, asset=BTC)}}


class MetricsTests(unittest.TestCase):
    def test_unknown_zero_and_nan(self):
        self.assertIsNone(number(None))
        self.assertEqual(number(0), 0)
        self.assertIsNone(change(0, 5))
        self.assertAlmostEqual(change(100, 110), 10)
        with self.assertRaises(ValueError): number("nan")
        with self.assertRaises(ValueError): instant("2026-01-01")

    def test_address_case(self):
        self.assertEqual(asset_key({"chain": "base", "address": "0x" + "A" * 40}),
                         asset_key({"chain": "base", "address": "0x" + "a" * 40}))
        self.assertNotEqual(asset_key({"chain": "solana", "address": "ABC"}),
                            asset_key({"chain": "solana", "address": "abc"}))
        with self.assertRaises(ValueError): asset_key({"chain": "ethereum", "address": "0xpool"})

    def test_sui_coin_identity(self):
        self.assertEqual(asset_key({"chain": "sui", "address": "0x2::sui::SUI"}), "sui:native:sui")
        self.assertEqual(asset_key({"chain": "sui", "address": "0xAb::m::C"}),
                         asset_key({"chain": "sui", "address": "0x" + "0" * 62 + "ab::m::C"}))
        self.assertNotEqual(asset_key({"chain": "sui", "address": "0xab::m::C"}),
                            asset_key({"chain": "sui", "address": "0xab::m::c"}))
        with self.assertRaises(ValueError): asset_key({"chain": "sui", "address": "0x" + "a" * 64})
        self.assertEqual(asset_key(ASSET), "ethereum:native:eth")

    def test_read_only_chain_probes(self):
        self.assertEqual(resolve_source({"kind": "rpc", "url": "https://example.com", "params": {"method": "eth_chainId"}})[2]["method"], "eth_chainId")
        with self.assertRaises(ValueError): resolve_source({"kind": "rpc", "url": "https://example.com", "params": {"method": "eth_sendRawTransaction"}})
        url, _, body = resolve_source({"kind": "sui-checkpoint"})
        self.assertEqual(url, "https://graphql.mainnet.sui.io/graphql")
        self.assertTrue(body["query"].startswith("query { checkpoint"))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("collect.request", return_value=(b'{"errors":[{"message":"bad field"}]}', "application/json")):
                result = fetch_one({"id": "sui", "kind": "sui-checkpoint"}, Path(tmp))
            self.assertEqual(result["status"], "error")
            self.assertTrue(Path(result["raw_path"]).exists())

    def test_concentration_exclusions_and_sample(self):
        data = {"chain": "solana", "total_supply": 1000, "holders": [
            {"address": "Pool", "balance": 500, "exclude": True, "label_source": "https://example.com"},
            {"address": "Alice", "balance": 200}, {"address": "Bob", "balance": 100}]}
        result = concentration(data)
        self.assertEqual(result["raw_top10_pct"], 80)
        self.assertEqual(result["adjusted_top10_pct"], 60)
        self.assertEqual(result["coverage"], "partial")
        del data["holders"][0]["label_source"]
        with self.assertRaises(ValueError): concentration(data)

    def test_no_fabricated_history(self):
        data = {"instrument": "fixture", "interval": "1d", "candles": [
            {"time": f"2026-01-{i:02d}T00:00:00Z", "close": i} for i in range(1, 16)]}
        result = candles(data)
        self.assertIsNone(result["sma_20"])
        self.assertEqual(result["rsi14_wilder"], 100)
        data["candles"].reverse()
        with self.assertRaises(ValueError): candles(data)

    def test_depth_partial_book_not_executable(self):
        result = depth({"quote_amount": 10000, "bids": [[99, 1]], "asks": [[101, 1]]})
        self.assertIsNone(result["buy_vwap"])
        self.assertIsNone(result["roundtrip_quote_return_pct"])

    def test_snapshot_comparability(self):
        a = {"asset": ASSET, "observed_at": "2026-01-01T00:00:00Z",
             "metrics": {"holders": {"value": 100, "unit": "addresses", "scope": "chain"}}}
        b = copy.deepcopy(a)
        b["observed_at"] = "2026-01-02T00:00:00Z"
        b["metrics"]["holders"]["value"] = 120
        self.assertEqual(delta({"before": a, "after": b})["metrics"]["holders"]["delta"], 20)
        b["metrics"]["holders"]["scope"] = "pool"
        with self.assertRaises(ValueError): delta({"before": a, "after": b})


class EvidenceTests(unittest.TestCase):
    def test_transport_invalid_types_raise_validation_error(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {}, clear=True):
            path = Path(folder) / "transport.json"
            for settings in ([], {"trusted_proxy_ip": None, "trusted_public_hosts": ["example.com"]},
                             {"trusted_proxy_ip": "198.18.0.1", "trusted_public_hosts": [123]}):
                path.write_text(json.dumps(settings))
                with self.assertRaises(ValueError): configure_transport(Path(folder))

    def test_platform_proxy_requires_exact_ip_and_named_host(self):
        env = {"CRYPTO_RESEARCH_PROXY_IP": "198.18.0.1", "CRYPTO_RESEARCH_PROXY_HOSTS": "api.dexscreener.com"}
        with patch.dict("os.environ", env, clear=True):
            with patch("collect.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("198.18.0.1", 443))]):
                self.assertEqual(public_url("https://api.dexscreener.com/"), "https://api.dexscreener.com/")
                with self.assertRaises(ValueError): public_url("https://unknown.example.com/")
            for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "198.18.0.2"):
                with patch("collect.socket.getaddrinfo", return_value=[(2, 1, 6, "", (ip, 443))]):
                    with self.assertRaises(ValueError): public_url("https://api.dexscreener.com/")

    def test_bad_proxy_configuration_is_rejected(self):
        with patch.dict("os.environ", {"CRYPTO_RESEARCH_PROXY_IP": "127.0.0.1", "CRYPTO_RESEARCH_PROXY_HOSTS": "api.dexscreener.com"}, clear=True):
            with self.assertRaises(ValueError): public_url("https://api.dexscreener.com/")
        with patch.dict("os.environ", {"CRYPTO_RESEARCH_PROXY_IP": "198.18.0.1", "CRYPTO_RESEARCH_PROXY_HOSTS": "*.com"}, clear=True):
            with self.assertRaises(ValueError): public_url("https://api.dexscreener.com/")

    def test_doctor_reports_network_degradation(self):
        with patch("research.request", side_effect=ValueError("Non-public address refused")):
            report = doctor(True)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["network"]["dexscreener"]["reason"], "Non-public address refused")

    def test_rpc_read_only(self):
        with self.assertRaises(ValueError): resolve_source({"kind": "rpc", "url": "https://example.com", "params": {"method": "eth_sendTransaction"}})

    def test_private_url_and_credentials(self):
        with self.assertRaises(ValueError): public_url("http://example.com")
        with self.assertRaises(ValueError): public_url("https://example.com?api_key=x")
        with patch("collect.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError): public_url("https://example.com")

    def test_cache_preserves_original_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            source = {"id": "one", "kind": "dex-search", "params": {"query": "ETH"}, "cache_ttl": 3600}
            with patch("collect.request", return_value=(b'{"pairs": []}', "application/json")) as req:
                first = fetch_one(source, Path(folder))
                second = fetch_one({**source, "id": "two"}, Path(folder))
            self.assertEqual(req.call_count, 1)
            self.assertEqual(first["retrieved_at"], second["retrieved_at"])
            self.assertTrue(second["cache_hit"])
            self.assertIsNone(first["observed_at"])

    def test_errors_do_not_become_zero_data(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("collect.request", side_effect=TimeoutError()):
                result = collect({"target": "ETH", "sources": [{"id": "p", "kind": "dex-search", "params": {"query": "ETH"}}]}, Path(folder))
            self.assertEqual(result["records"][0]["status"], "error")
            self.assertNotIn("data", result["records"][0])
            self.assertEqual(len(result["gaps"]), 1)

    def test_native_dedup_preserves_provenance(self):
        native = import_native({"records": [{"evidence_id": "x1", "url": "https://x.com/a/status/1",
            "retrieved_at": "2026-01-01T00:00:00Z", "content": "actual captured post", "tool": "x.search_posts_all"}]})
        two = {**native[0], "evidence_id": "x2", "url": "https://x.com/b/status/2"}
        result = prepare({"records": native}, [two])
        self.assertEqual(result["records"][1]["duplicate_of"], "x1")
        self.assertEqual(result["records"][1]["url"], "https://x.com/b/status/2")
        with self.assertRaises(ValueError): import_native({"records": [{"evidence_id": "bad", "url": "https://x.com"}]})


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_immutable_due_and_hash_chain(self):
        original = record_decision(decision(), EVIDENCE, self.root)
        self.assertEqual(len(due(self.root, "2026-01-30T23:59:59Z")), 0)
        self.assertEqual(len(due(self.root, "2026-01-31T00:00:00Z")), 1)
        with self.assertRaises(ValueError): record_decision(decision(), EVIDENCE, self.root)
        self.assertEqual(audit(self.root)["entries"], 1)
        path = self.root / "judgments.jsonl"
        path.write_text(path.read_text().replace('"high"', '"low"'))
        with self.assertRaises(ValueError): audit(self.root)

    def test_separate_direction_relative_and_no_watch_win(self):
        original = record_decision(decision(), EVIDENCE, self.root)
        review = {"horizon_days": 30, "reviewed_at": "2026-01-31T01:00:00Z",
                  "quote": quote(110, "2026-01-31T00:00:00Z"),
                  "benchmark_quote": quote(120, "2026-01-31T00:00:00Z", BTC)}
        result = outcome(original, review, EVIDENCE)
        self.assertTrue(result["direction_hit"])
        self.assertFalse(result["relative_direction_hit"])
        self.assertAlmostEqual(result["excess_return_pp"], -10)
        original["signal"] = "WATCH"
        self.assertIsNone(outcome(original, review, EVIDENCE)["direction_hit"])
        original["signal"] = "SELL"
        self.assertFalse(outcome(original, review, EVIDENCE)["direction_hit"])

    def test_pending_retry_complete_idempotency(self):
        record_decision(decision(), EVIDENCE, self.root)
        review = {"decision_id": "eth-20260101", "horizon_days": 30, "authored_by": "model",
                  "execution_agent": "test-fixture", "model": "unknown", "reviewed_at": "2026-01-31T01:00:00Z",
                  "assessment": "Fixture review", "status": "pending_data", "data_gap": "No quote", "benchmark_gap": "No benchmark"}
        record_review(review, EVIDENCE, self.root)
        self.assertEqual(len(due(self.root, "2026-01-31T02:00:00Z")), 1)
        review.update(status="complete", quote=quote(90, "2026-01-31T00:00:00Z"),
                      benchmark_quote=quote(100, "2026-01-31T00:00:00Z", BTC),
                      assertion_results=[{"id": "event1", "status": "unknown"}])
        record_review(review, EVIDENCE, self.root)
        self.assertEqual(len(due(self.root, "2026-01-31T02:00:00Z")), 0)
        self.assertEqual(summary(self.root)["groups"]["30d_BUY"]["n"], 1)
        with self.assertRaises(ValueError): record_review(review, EVIDENCE, self.root)

    def test_future_stale_wrong_asset_and_unsourced(self):
        value = decision()
        value["reference_quote"]["observed_at"] = "2025-12-31T23:00:00Z"
        with self.assertRaises(ValueError): record_decision(value, EVIDENCE, self.root)
        value = decision()
        value["evidence_refs"] = ["missing"]
        with self.assertRaises(ValueError): record_decision(value, EVIDENCE, self.root)
        original = record_decision(decision(), EVIDENCE, self.root)
        review = {"horizon_days": 30, "reviewed_at": "2026-01-31T00:00:00Z", "quote": quote(110, "2026-02-05T00:00:00Z")}
        with self.assertRaises(ValueError): outcome(original, review, EVIDENCE)

    def test_missing_benchmark_cannot_close_temporary_gap(self):
        record_decision(decision(), EVIDENCE, self.root)
        review = {"decision_id": "eth-20260101", "horizon_days": 30, "authored_by": "model",
                  "execution_agent": "fixture", "model": "unknown", "reviewed_at": "2026-01-31T01:00:00Z",
                  "assessment": "Missing benchmark", "status": "complete", "quote": quote(110, "2026-01-31T00:00:00Z"),
                  "assertion_results": [{"id": "event1", "status": "unknown"}]}
        with self.assertRaises(ValueError): record_review(review, EVIDENCE, self.root)
        review["benchmark_gap"] = "Temporarily unavailable"
        with self.assertRaises(ValueError): record_review(review, EVIDENCE, self.root)
        review["status"] = "pending_data"
        review["data_gap"] = "Benchmark unavailable"
        record_review(review, EVIDENCE, self.root)
        self.assertEqual(len(due(self.root, "2026-01-31T02:00:00Z")), 1)
        review["status"] = "complete"
        review["final_data_unavailable_reason"] = "Fixture permanent loss of source"
        record_review(review, EVIDENCE, self.root)
        self.assertEqual(summary(self.root)["groups"]["30d_BUY"]["relative_not_evaluable"], 1)

    def test_changed_venue_or_instrument_not_scored(self):
        original = record_decision(decision(), EVIDENCE, self.root)
        endpoint = quote(10000, "2026-01-31T00:00:00Z")
        review = {"horizon_days": 30, "reviewed_at": "2026-01-31T01:00:00Z", "quote": endpoint}
        endpoint["venue"] = "unrelated-illiquid-pool"
        with self.assertRaises(ValueError): outcome(original, review, EVIDENCE)
        endpoint["venue"] = "fixture"
        endpoint["instrument"] = "wrapped-ETHUSD"
        with self.assertRaises(ValueError): outcome(original, review, EVIDENCE)
        review["quote"] = quote(110, "2026-01-31T00:00:00Z", BTC)
        with self.assertRaises(ValueError): outcome(original, review, EVIDENCE)


if __name__ == "__main__":
    unittest.main()
