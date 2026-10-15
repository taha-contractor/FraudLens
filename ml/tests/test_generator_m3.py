"""Tests for the M3 CSV-only generator + pilot pipeline.

Run from the repo root (with the ML source on PYTHONPATH), using the project Python env:
    $env:PYTHONPATH="ml/src"; python -m unittest discover -s ml/tests -t ml/tests

Heavy source access is mocked except the single raw-preservation fingerprint test, so
the suite stays fast and deterministic while still exercising CSV write/read,
provenance integrity, leakage guards, coverage, balance and chain consistency.
"""

import copy
import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "ml" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data import origindata  # noqa: E402
from generator import config, emitter, pipeline, schema, validate  # noqa: E402


def write_temp_source_csv(path: str, n_rows: int) -> list:
    """Write a small PaySim-shaped source CSV (header + ``n_rows`` verbatim rows).

    Returns the list of row dicts written, so callers can assert streaming
    fidelity without re-deriving the values. Values are distinct per row so a
    mis-order or partial read is caught.
    """
    rows = []
    for i in range(n_rows):
        rows.append({
            "step": str(1 + i % 743), "type": "TRANSFER" if i % 5 == 0 else "PAYMENT",
            "amount": f"{i + 0.5:.2f}", "nameOrig": f"C{i:010d}",
            "oldbalanceOrg": f"{i * 1.5:.2f}", "newbalanceOrig": f"{i * 1.5:.2f}",
            "nameDest": f"M{i:010d}", "oldbalanceDest": "0.00", "newbalanceDest": "0.00",
            "isFraud": "1" if i % 50 == 0 else "0", "isFlaggedFraud": "0",
        })
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=origindata.EXPECTED_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return rows


def small_config(**over):
    d = copy.deepcopy(config.DEFAULT_CONFIG)
    d["generated_rows"] = over.get("generated_rows", 6000)
    d["n_origin_accounts"] = over.get("n_origin_accounts", 500)
    d["n_dest_accounts"] = over.get("n_dest_accounts", 200)
    d["min_per_scenario_count"] = over.get("min_per_scenario_count", 1)
    return config.GeneratorConfig.from_dict(d)


# A minimal PaySim-shaped source row for the original-mapping tests (verbatim text).
_FAKE_SOURCE_ROW = {
    "source_row_index": 12345,
    "step": "300", "type": "CASH_OUT", "amount": "12345.67",
    "nameOrig": "C1234567890", "oldbalanceOrg": "500.0", "newbalanceOrig": "0.0",
    "nameDest": "M9876543210", "oldbalanceDest": "0.0", "newbalanceDest": "0.0",
    "isFraud": "1", "isFlaggedFraud": "0",
}


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_identical_output(self):
        a = emitter.TransactionEmitter(small_config()).emit()
        b = emitter.TransactionEmitter(small_config()).emit()
        self.assertEqual(a, b)

    def test_different_seed_different_output(self):
        d1 = small_config(); d1.master_seed = 7
        d2 = small_config(); d2.master_seed = 8
        a = emitter.TransactionEmitter(d1.validate()).emit()
        b = emitter.TransactionEmitter(d2.validate()).emit()
        self.assertNotEqual([r["record_uid"] for r in a], [r["record_uid"] for r in b])

    def test_record_uids_unique(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        uids = [r["record_uid"] for r in recs]
        self.assertEqual(len(uids), len(set(uids)))


class SchemaAndLabelTests(unittest.TestCase):
    def test_emitter_schema_matches_generated_record_columns(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        self.assertEqual(set(recs[0]), set(schema.GENERATED_RECORD_COLUMNS))

    def test_mapped_row_schema_matches_enhanced_csv(self):
        gen = emitter.TransactionEmitter(small_config(generated_rows=60)).emit()
        for r in gen:
            self.assertEqual(set(pipeline._generated_to_row(r)),
                             set(schema.ENHANCED_FEATURE_COLUMNS))

    def test_labels_binary(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        self.assertTrue(all(r["is_fraud"] in (0, 1) for r in recs))

    def test_valid_types(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        self.assertTrue(all(r["type"] in schema.TRANSACTION_TYPES for r in recs))

    def test_non_negative_amounts_and_origin_balances(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        for r in recs:
            self.assertGreaterEqual(r["amount"], 0)
            self.assertGreaterEqual(r["oldbalanceOrg"], -1e-9)
            self.assertGreaterEqual(r["newbalanceOrig"], -1e-9)


class CoverageTests(unittest.TestCase):
    def test_all_types_have_legit_and_fraud(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        for t in schema.TRANSACTION_TYPES:
            fraud = [r for r in recs if r["type"] == t and r["is_fraud"] == 1]
            legit = [r for r in recs if r["type"] == t and r["is_fraud"] == 0]
            self.assertTrue(fraud, f"no fraud for {t}")
            self.assertTrue(legit, f"no legit for {t}")

    def test_fraud_rate_near_target(self):
        cfg = small_config(generated_rows=40000)
        recs = emitter.TransactionEmitter(cfg).emit()
        rate = sum(r["is_fraud"] for r in recs) / len(recs)
        self.assertLess(rate, 2 * cfg.overall_fraud_rate)
        self.assertGreater(rate, cfg.overall_fraud_rate / 2)


class ConsistencyTests(unittest.TestCase):
    def test_balance_identity(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        tol = 0.01
        for r in recs:
            delta = r["amount"] if r["type"] == "CASH_IN" else -r["amount"]
            self.assertLessEqual(abs(r["oldbalanceOrg"] + delta - r["newbalanceOrig"]), tol + 1e-9)

    def test_repeated_accounts_exist(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        origins = [r["nameOrig"] for r in recs]
        # far more transactions than distinct accounts -> histories are reused
        self.assertGreater(len(origins), len(set(origins)))

    def test_chains_grouped_and_consistent(self):
        recs = emitter.TransactionEmitter(small_config()).emit()
        groups = {}
        for r in recs:
            if r["chain_id"]:
                groups.setdefault(r["chain_id"], []).append(r)
        self.assertTrue(groups, "expected some linked chains")
        for cid, rows in groups.items():
            self.assertGreaterEqual(len(rows), 2, cid)
            self.assertEqual(len({x["is_fraud"] for x in rows}), 1, cid)

    def test_gates_pass(self):
        cfg = small_config()
        recs = emitter.TransactionEmitter(cfg).emit()
        self.assertEqual(validate.ValidationHarness(cfg).run_dataset_gates(recs), [])


class OriginalMappingTests(unittest.TestCase):
    def test_labels_preserved_and_no_fabricated_timestamp(self):
        row = pipeline._original_to_row(_FAKE_SOURCE_ROW)
        self.assertEqual(row["isFraud"], "1")          # verbatim, not coerced
        self.assertEqual(row["isFlaggedFraud"], "0")
        self.assertEqual(row["event_ts"], "")          # original has no sub-day time
        self.assertEqual(row["amount"], "12345.67")    # text preserved exactly

    def test_record_uid_stable(self):
        a = pipeline._original_to_row(_FAKE_SOURCE_ROW)["record_uid"]
        b = pipeline._original_to_row(_FAKE_SOURCE_ROW)["record_uid"]
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("o-"))


class CsvRoundTripTests(unittest.TestCase):
    def test_write_then_read_preserves_strings(self):
        rows = [pipeline._original_to_row(_FAKE_SOURCE_ROW)]
        gen = emitter.TransactionEmitter(small_config(generated_rows=60)).emit()[:5]
        rows += [pipeline._generated_to_row(r) for r in gen]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.csv")
            n = pipeline._write_csv_chunked(path, schema.ENHANCED_FEATURE_COLUMNS, rows, chunksize=2)
            self.assertEqual(n, len(rows))
            with open(path, newline="", encoding="utf-8") as fh:
                header = fh.readline().rstrip("\n").split(",")
            self.assertEqual(header, schema.ENHANCED_FEATURE_COLUMNS)
            back = list(pipeline.iter_enhanced_csv(path, chunksize=2))
            got = [r for chunk in back for r in chunk.to_dict("records")]
            self.assertEqual(len(got), len(rows))
            self.assertEqual(got[0]["amount"], "12345.67")   # no float coercion
            self.assertEqual(got[0]["isFraud"], "1")

    def test_money_serialization_deterministic(self):
        self.assertEqual(pipeline.money(1234.5), "1234.50")
        self.assertEqual(pipeline.money(0), "0.00")

    def test_newline_is_lf(self):
        gen = emitter.TransactionEmitter(small_config(generated_rows=60)).emit()[:3]
        rows = [pipeline._generated_to_row(r) for r in gen]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.csv")
            pipeline._write_csv_chunked(path, schema.ENHANCED_FEATURE_COLUMNS, rows)
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r\n", fh.read())  # no CRLF


class PipelineIntegrationTests(unittest.TestCase):
    """End-to-end pilot with the multi-hundred-MB source mocked out."""

    def test_generate_pilot_writes_csv_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(origindata, "verify_integrity",
                                   return_value={"sha256": "X", "size_bytes": 1, "path": "p"}), \
                 mock.patch.object(origindata, "load_original_sample",
                                   return_value=[_FAKE_SOURCE_ROW, dict(_FAKE_SOURCE_ROW, source_row_index=999, isFraud="0")]):
                summary = pipeline.generate_pilot(d, config=small_config(), n_generated=6000, n_original=2)
            tx_path = summary["output_files"]["transactions"]
            pv_path = summary["output_files"]["provenance"]
            self.assertTrue(os.path.exists(tx_path))
            self.assertTrue(os.path.exists(pv_path))
            self.assertTrue(os.path.exists(summary["output_files"]["manifest"]))
            # no parquet anywhere
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".parquet")])

            with open(tx_path, newline="", encoding="utf-8") as fh:
                tx_rows = list(csv.DictReader(fh))
            with open(pv_path, newline="", encoding="utf-8") as fh:
                pv_rows = list(csv.DictReader(fh))

            # one provenance row per transaction, joined by record_uid
            self.assertEqual(len(tx_rows), len(pv_rows))
            self.assertEqual({r["record_uid"] for r in tx_rows}, {p["record_uid"] for p in pv_rows})

            # transaction CSV never exposes provenance/leakage columns
            forbidden = set(schema.PROVENANCE_COLUMNS) - {"record_uid"}
            for col in forbidden:
                self.assertNotIn(col, tx_rows[0])

            # original rows: scenario_id empty; generated rows: scenario_id set
            orig_pv = [p for p in pv_rows if p["record_origin"] == "original"]
            gen_pv = [p for p in pv_rows if p["record_origin"] == "generated"]
            self.assertTrue(all(not p["scenario_id"] for p in orig_pv))
            self.assertTrue(all(p["scenario_id"] for p in gen_pv))
            self.assertEqual(len(orig_pv), 2)

    def test_pilot_reproducible(self):
        blobs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                with mock.patch.object(origindata, "verify_integrity",
                                       return_value={"sha256": "X", "size_bytes": 1, "path": "p"}), \
                     mock.patch.object(origindata, "load_original_sample",
                                       return_value=[_FAKE_SOURCE_ROW]):
                    pipeline.generate_pilot(d, config=small_config(), n_generated=4000, n_original=1)
                    with open(os.path.join(d, "enhanced_transactions.csv"), "rb") as fh:
                        blobs.append(fh.read())
        self.assertEqual(blobs[0], blobs[1])


class LeakageGuardTests(unittest.TestCase):
    def test_pretransaction_excludes_oracle_and_future(self):
        feats = set(schema.pre_transaction_feature_columns())
        for bad in ["isFraud", "isFlaggedFraud", "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest"]:
            self.assertNotIn(bad, feats)

    def test_generated_never_sets_flagged_fraud(self):
        gen = emitter.TransactionEmitter(small_config()).emit()
        for r in gen[:200]:
            row = pipeline._generated_to_row(r)
            self.assertEqual(row["isFlaggedFraud"], 0)

    def test_feature_provenance_disjoint(self):
        schema.assert_feature_provenance_disjoint()


class RawPreservationTests(unittest.TestCase):
    def test_source_checksum_unchanged(self):
        # streaming SHA-256 of the real read-only source must still match the frozen value
        fp = origindata.verify_integrity()
        self.assertEqual(fp["sha256"], origindata.EXPECTED_SHA256)


class FraudRateMathTests(unittest.TestCase):
    """Task 1: the realised fraud math must equal the configured math, exactly.

    Regression guard for the dilution bug where chain rows were re-added to
    LEGIT scenarios, inflating every per-type denominator by ~1% and dropping
    the overall rate from 3.02% to 2.99%.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg = small_config(generated_rows=60000)
        cls.recs = emitter.TransactionEmitter(cls.cfg).emit()
        cls.by_type = {t: [r for r in cls.recs if r["type"] == t] for t in schema.TRANSACTION_TYPES}

    def _expected_overall(self):
        w = self.cfg.type_weights
        r = self.cfg.fraud_rate_by_type
        return sum(w[t] * r[t] for t in w) / sum(w.values())

    def test_realized_per_type_rate_matches_config(self):
        for t, rows in self.by_type.items():
            total = len(rows)
            fraud = sum(x["is_fraud"] for x in rows)
            target = self.cfg.fraud_rate_by_type[t]
            # allocator targets round(total * rate); realised may differ by <=1 row
            self.assertLessEqual(abs(fraud - round(total * target)), 1,
                                 f"{t}: fraud {fraud} vs round({total}*{target})")
            self.assertLessEqual(abs(fraud / total - target), 1.5 / total,
                                 f"{t}: realised rate {fraud/total} != config {target}")

    def test_realized_overall_matches_weighted_expectation(self):
        fraud = sum(x["is_fraud"] for x in self.recs)
        realised = fraud / len(self.recs)
        expected = self._expected_overall()
        self.assertAlmostEqual(expected, 0.0302, places=4)
        self.assertLessEqual(abs(realised - expected), 1.0 / len(self.recs) + 1e-9,
                             f"overall {realised} != expected {expected}")

    def test_chain_fraud_counted_within_budget_not_added_on_top(self):
        chain_rows = [x for x in self.recs if x["chain_id"]]
        self.assertTrue(chain_rows, "expected some fraud chains")
        # chains flow only through TRANSFER / CASH_OUT (never inflate rare-fraud types)
        self.assertTrue(all(x["type"] in ("TRANSFER", "CASH_OUT") for x in chain_rows))
        self.assertTrue(all(x["is_fraud"] == 1 for x in chain_rows))
        # per-type fraud totals already INCLUDE chain rows (not stacked on top)
        for t in ("TRANSFER", "CASH_OUT"):
            fraud = sum(x["is_fraud"] for x in self.by_type[t])
            chain_in_t = sum(1 for x in chain_rows if x["type"] == t)
            self.assertLessEqual(chain_in_t, fraud,
                                 f"{t}: chain fraud {chain_in_t} exceeds type fraud {fraud}")
        # overall realised equals weighted expectation confirms no dilution
        self.assertLessEqual(abs(sum(x["is_fraud"] for x in self.recs) / len(self.recs)
                                 - self._expected_overall()), 1.0 / len(self.recs) + 1e-9)


class FullSourceInclusionTests(unittest.TestCase):
    """Task 2: distinguish pilot sampling from full-source inclusion."""

    def test_iter_source_records_yields_every_row_verbatim(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            written = write_temp_source_csv(src, 137)
            got = list(origindata.iter_source_records(src, chunksize=10))
            self.assertEqual(len(got), 137)                     # no sampling / truncation
            self.assertEqual([r["source_row_index"] for r in got], list(range(137)))
            for g, w in zip(got, written):
                for col in origindata.EXPECTED_COLUMNS:
                    self.assertEqual(g[col], w[col])            # verbatim text, in order

    def test_load_original_sample_returns_strict_subset(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            write_temp_source_csv(src, 200)
            sample = origindata.load_original_sample(src, n=20, n_fraud=2, chunksize=50)
            self.assertLess(len(sample), 200)                   # sampling, not full inclusion
            self.assertTrue(all(0 <= r["source_row_index"] < 200 for r in sample))
            self.assertEqual(len(sample), len({r["source_row_index"] for r in sample}))

    def test_full_source_inclusion_streams_all_originals(self):
        cfg = small_config(generated_rows=6000)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            write_temp_source_csv(src, 500)
            out = os.path.join(d, "out")
            with mock.patch.object(origindata, "verify_integrity", return_value={"sha256": "X", "size_bytes": 1, "path": src}):
                summary = pipeline.generate_enhanced_dataset(
                    out, cfg, include_original="all", source_path=src)
            self.assertEqual(summary["counts"]["original_rows"], 500)   # every source row present
            with open(summary["output_files"]["transactions"], newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(summary["counts"]["transactions_written"], len(rows))
            self.assertEqual(len(rows), 6000 + 500)                    # generated + ALL originals
            origs = [r for r in rows if r["record_uid"].startswith("o-")]
            self.assertEqual(len(origs), 500)
            self.assertTrue(all(r["event_ts"] == "" for r in origs))   # no fabricated timestamps

    def test_source_file_never_modified_by_inclusion(self):
        cfg = small_config(generated_rows=6000)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            write_temp_source_csv(src, 250)
            with open(src, "rb") as fh:
                before = fh.read()
            with mock.patch.object(origindata, "verify_integrity", return_value={"sha256": "X", "size_bytes": len(before), "path": src}):
                pipeline.generate_enhanced_dataset(os.path.join(d, "out"), cfg,
                                                   include_original="all", source_path=src)
            with open(src, "rb") as fh:
                self.assertEqual(fh.read(), before)                    # byte-for-byte unchanged


class StreamingWriterTests(unittest.TestCase):
    """Task 4: streaming writer is iterator-driven and byte-reproducible."""

    def test_stream_matches_materialized_bytes(self):
        gen = emitter.TransactionEmitter(small_config(generated_rows=200)).emit()
        rows = [pipeline._generated_to_row(r) for r in gen]
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.csv")
            b = os.path.join(d, "b.csv")
            n1 = pipeline.write_csv_stream(a, schema.ENHANCED_FEATURE_COLUMNS, iter(rows))
            n2 = pipeline._write_csv_chunked(b, schema.ENHANCED_FEATURE_COLUMNS, rows)
            self.assertEqual(n1, len(rows))
            self.assertEqual(n2, len(rows))
            with open(a, "rb") as fa, open(b, "rb") as fb:
                self.assertEqual(fa.read(), fb.read())

    def test_chunk_size_does_not_change_output_bytes(self):
        gen = emitter.TransactionEmitter(small_config(generated_rows=300)).emit()
        rows = [pipeline._generated_to_row(r) for r in gen]
        blobs = []
        with tempfile.TemporaryDirectory() as d:
            for cs in (1, 7, 128, 10_000):
                p = os.path.join(d, f"c{cs}.csv")
                pipeline.write_csv_stream(p, schema.ENHANCED_FEATURE_COLUMNS, iter(rows), chunksize=cs)
                with open(p, "rb") as fh:
                    blobs.append(fh.read())
        self.assertTrue(all(x == blobs[0] for x in blobs))            # buffer boundary irrelevant

    def test_streaming_output_is_temp_published_and_lf_only(self):
        gen = emitter.TransactionEmitter(small_config(generated_rows=100)).emit()
        rows = [pipeline._generated_to_row(r) for r in gen]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            pipeline.write_csv_stream(p, schema.ENHANCED_FEATURE_COLUMNS, iter(rows))
            self.assertFalse(os.path.exists(p + ".tmp"))              # temp renamed away
            with open(p, "rb") as fh:
                self.assertNotIn(b"\r\n", fh.read())                  # LF newlines only


if __name__ == "__main__":
    unittest.main()
