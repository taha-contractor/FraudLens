"""Scale-readiness tests for the bounded-memory streaming generator (M3).

Run from the repo root:
    python -m unittest discover -s ml/tests -t ml/tests

These exercise the full-scale path at a *moderate* workload so the suite stays fast,
asserting the properties the ~2M run depends on: streaming == materialised output,
determinism, bucket-span invariance, genuinely lower peak memory, and the fraud /
coverage / balance / chain / provenance invariants driven through the single-pass
GenStats accumulator. Actual peak-memory and throughput figures at large scale are
measured by ``ml/measure_scale.py`` and reported separately (not extrapolated here).
"""

import copy
import hashlib
import os
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "ml" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generator import config, emitter, pipeline, schema  # noqa: E402
from generator.stats import GenStats  # noqa: E402


def make_config(**over):
    d = copy.deepcopy(config.DEFAULT_CONFIG)
    d["generated_rows"] = over.get("generated_rows", 60_000)
    d["n_origin_accounts"] = over.get("n_origin_accounts", 200_000)
    d["n_dest_accounts"] = over.get("n_dest_accounts", 80_000)
    d["min_per_scenario_count"] = over.get("min_per_scenario_count", 1)
    return config.GeneratorConfig.from_dict(d)


def stream_to_csv(cfg, bucket_span=12):
    """Stream generated records to a temp CSV; return (sha256, row_count)."""
    digest = hashlib.sha256()
    n = 0
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as out:
        path = os.path.join(out, "t.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            import csv as _csv
            w = _csv.DictWriter(fh, fieldnames=schema.ENHANCED_FEATURE_COLUMNS, lineterminator="\n")
            w.writeheader()
            for r in emitter.TransactionEmitter(cfg).emit_stream(work, bucket_span=bucket_span):
                line = ",".join(str(v) for v in pipeline._generated_to_row(r).values()) + "\n"
                fh.write(line)
                digest.update(line.encode("utf-8"))
                n += 1
        return digest.hexdigest(), n


class StreamEquivalenceTests(unittest.TestCase):
    def test_stream_matches_materialised_output(self):
        cfg = make_config(generated_rows=8000)
        listed = emitter.TransactionEmitter(cfg).emit()
        with tempfile.TemporaryDirectory() as work:
            streamed = list(emitter.TransactionEmitter(cfg).emit_stream(work))
        self.assertEqual(len(streamed), len(listed))
        self.assertEqual(streamed, listed)          # byte-for-byte equal records & order

    def test_stream_is_deterministic_bytes(self):
        cfg = make_config(generated_rows=8000)
        h1, n1 = stream_to_csv(cfg)
        h2, n2 = stream_to_csv(cfg)
        self.assertEqual((h1, n1), (h2, n2))

    def test_bucket_span_does_not_change_dataset_or_order(self):
        cfg = make_config(generated_rows=8000)
        results = [stream_to_csv(cfg, bucket_span=span) for span in (1, 5, 12, 60)]
        self.assertTrue(all(h == results[0][0] and n == results[0][1] for h, n in results),
                        "bucket_span changed the logical dataset or ordering")


class BoundedMemoryTests(unittest.TestCase):
    def test_stream_peak_memory_below_materialised(self):
        # Rows >> accounts so the row set (not the fixed ledger) dominates memory.
        cfg = make_config(generated_rows=60_000, n_origin_accounts=5_000, n_dest_accounts=2_000)

        with tempfile.TemporaryDirectory() as work:
            tracemalloc.start()
            streamed_n = sum(1 for _ in emitter.TransactionEmitter(cfg).emit_stream(work))
            _, stream_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

        tracemalloc.start()
        listed = emitter.TransactionEmitter(cfg).emit()
        _, list_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.assertEqual(streamed_n, len(listed))
        # Streaming holds ~one bucket, not the whole run: peak must be materially lower.
        self.assertLess(stream_peak, list_peak,
                        f"stream peak {stream_peak} not below materialised peak {list_peak}")


class ScaleInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = make_config(generated_rows=60_000)
        cls.stats = GenStats(tol=cls.cfg.ledger_tolerance, track_uids=True)
        seen_uids = set()
        dup = 0
        with tempfile.TemporaryDirectory() as work:
            for r in emitter.TransactionEmitter(cls.cfg).emit_stream(work):
                cls.stats.add(r)
                if r["record_uid"] in seen_uids:
                    dup += 1
                seen_uids.add(r["record_uid"])
        cls.dup_uids = dup

    def test_fraud_rate_matches_expected(self):
        expected = sum(self.cfg.type_weights[t] * self.cfg.fraud_rate_by_type[t]
                       for t in self.cfg.type_weights) / sum(self.cfg.type_weights.values())
        self.assertAlmostEqual(self.stats.fraud / self.stats.total, expected, delta=1e-6)

    def test_per_type_rates_match_config(self):
        for t, total in self.stats.type_counts.items():
            fraud = self.stats.fraud_by_type[t]
            self.assertLessEqual(abs(fraud - round(total * self.cfg.fraud_rate_by_type[t])), 1, t)

    def test_all_scenarios_and_types_covered(self):
        from generator.scenarios import ScenarioLibrary
        expected = {s.scenario_id for s in ScenarioLibrary().scenarios}
        self.assertEqual(expected, set(self.stats.scenario_counts))
        self.assertEqual(set(self.stats.fraud_by_type), set(schema.TRANSACTION_TYPES))
        self.assertTrue(all(n > 0 for n in self.stats.fraud_by_type.values()))
        self.assertTrue(all(n > 0 for n in self.stats.legit_by_type.values()))

    def test_balance_consistency(self):
        self.assertEqual(self.stats.bad_balance, 0)
        self.assertEqual(self.stats.neg_amount, 0)
        self.assertEqual(self.stats.neg_newbalance, 0)

    def test_chain_integrity(self):
        self.assertGreater(self.stats.chain_rows, 0)
        self.assertEqual(sum(1 for e in self.stats.chains.values() if e[0] < 2), 0)
        self.assertEqual(sum(1 for e in self.stats.chains.values() if not e[2]), 0)

    def test_provenance_completeness(self):
        self.assertEqual(self.stats.missing_scenario, 0)
        self.assertEqual(self.stats.missing_uid, 0)

    def test_record_uids_unique(self):
        self.assertEqual(self.dup_uids, 0)


class GatedPipelineAtScaleTests(unittest.TestCase):
    def test_full_source_stream_publishes_and_gates(self):
        from data import origindata
        from unittest import mock
        cfg = make_config(generated_rows=6000)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            rows = []
            import csv as _csv
            with open(src, "w", newline="", encoding="utf-8") as fh:
                w = _csv.DictWriter(fh, fieldnames=origindata.EXPECTED_COLUMNS, lineterminator="\n")
                w.writeheader()
                for i in range(400):
                    row = {"step": str(1 + i % 743), "type": "TRANSFER", "amount": f"{i}.50",
                           "nameOrig": f"C{i:010d}", "oldbalanceOrg": "0.00", "newbalanceOrig": "0.00",
                           "nameDest": f"M{i:010d}", "oldbalanceDest": "0.00", "newbalanceDest": "0.00",
                           "isFraud": "0", "isFlaggedFraud": "0"}
                    w.writerow(row)
                    rows.append(row)
            out = os.path.join(d, "out")
            with mock.patch.object(origindata, "verify_integrity",
                                   return_value={"sha256": "X", "size_bytes": 1, "path": src}):
                summary = pipeline.generate_enhanced_dataset(out, cfg, include_original="all", source_path=src)
            self.assertEqual(summary["counts"]["original_rows"], 400)
            self.assertEqual(summary["counts"]["transactions_written"], 6000 + 400)
            # At small N the largest-remainder allocation rounds each type's fraud
            # count to an integer, so the realised aggregate rate matches the config
            # target only within <=1 row per type (the tight 1e-6 equality is
            # asserted at 60k in ScaleInvariantTests). delta covers 5 rows / 6000.
            self.assertAlmostEqual(summary["counts"]["generated_fraud_rate"],
                                   summary["expected_fraud_rate"], delta=1e-3)
            self.assertFalse([f for f in os.listdir(out) if f.endswith(".parquet")])


if __name__ == "__main__":
    unittest.main()
