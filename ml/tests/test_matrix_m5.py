"""Equivalence: BoundedCausalBuilder == CausalFeatureBuilder on a realistic feed.

The full matrix build must reproduce, exactly, the features the M4 reference builder
produces, while staying bounded in memory. This feeds a MIXED stream — original-like
rows (empty event_ts -> causal clock = step*DAY, i.e. 1970) and generated-like rows
(real 2017 timestamps) — ordered globally by (step, ts, record_uid), exactly as
features.matrix._iter_step_sorted yields, across overlapping step ranges. Per-account
time is monotonic while the global order is NOT, which is the case that a naive global
window gets wrong.
"""

import os
import sys
import csv
import random
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from features.causal import CausalFeatureBuilder, causal_seconds, iter_time_sorted  # noqa: E402
from features.matrix import BoundedCausalBuilder, build_matrix, MODEL_MATRIX_COLUMNS  # noqa: E402
from features.policies import HISTORY_FEATURES  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"


def _mixed_rows(n=9000, seed=11):
    rng = random.Random(seed)
    base = datetime(2017, 6, 1)
    origins = ["C_ORIG_%d" % i for i in range(30)] + ["C_GEN_%d" % i for i in range(30)]
    dests = ["D_ORIG_%d" % i for i in range(20)] + ["D_GEN_%d" % i for i in range(20)]
    rows = []
    for i in range(n):
        step = rng.randint(1, 743)
        is_generated = i % 2 == 0
        if is_generated:
            # real 2017 clock, increasing-ish with step (hour per step)
            ts = base + timedelta(hours=step, seconds=rng.randint(0, 3599))
            event_ts = ts.strftime(FMT)
        else:
            event_ts = ""  # original -> causal_seconds = step*DAY (1970)
        rows.append({
            "record_uid": "U%08d" % i,
            "step": str(step),
            "event_ts": event_ts,
            "type": rng.choice(["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"]),
            "amount": "%.2f" % rng.uniform(0, 20000),
            "nameOrig": rng.choice(origins),
            "nameDest": rng.choice(dests),
            "isFraud": rng.choice(["0", "1"]),
        })
    # global order exactly as _iter_step_sorted produces (step primary, then ts, uid)
    rows.sort(key=lambda r: (int(r["step"]), causal_seconds(r), r["record_uid"]))
    return rows


class BoundedCausalEquivalenceTests(unittest.TestCase):
    def test_identical_features_on_mixed_causal_stream(self):
        rows = _mixed_rows()
        ref = CausalFeatureBuilder()
        bnd = BoundedCausalBuilder()
        for r in rows:
            a = ref.add(dict(r))
            b = bnd.add(dict(r))
            self.assertEqual(a, b, msg=f"mismatch at {r['record_uid']}")

    def test_lifetime_and_window_fields_all_present(self):
        rows = _mixed_rows(500)
        bnd = BoundedCausalBuilder()
        last = bnd.add(rows[0])
        self.assertEqual(
            set(last),
            {"origin_txn_count_prev", "origin_avg_amount_prev", "origin_amount_dev_prev",
             "origin_time_since_prev_txn", "origin_txn_last24h", "origin_amount_last24h",
             "origin_unique_dests_last24h", "dest_txn_count_prev", "dest_unique_origins_prev"})


class BuildMatrixEquivalenceTests(unittest.TestCase):
    """The compact array build path must equal the reference streaming builder."""

    def _write_tx(self, path, rows):
        cols = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "nameDest",
                "newbalanceOrig", "newbalanceDest", "isFraud", "isFlaggedFraud",
                "event_ts", "record_uid"]
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for r in rows:
                w.writerow([r["step"], r["type"], r["amount"], r["nameOrig"],
                            "1000.00", r["nameDest"], "0.00", "0.00", r["isFraud"],
                            "0", r["event_ts"], r["record_uid"]])

    def test_build_matrix_matches_reference(self):
        rng = random.Random(3)
        base = datetime(2017, 6, 1)
        origins = ["C%d" % i for i in range(25)]
        dests = ["D%d" % i for i in range(15)]
        rows = []
        for i in range(4000):
            step = rng.randint(1, 743)
            if i % 2:
                event_ts = (base + timedelta(hours=step, seconds=rng.randint(0, 3599))).strftime(FMT)
            else:
                event_ts = ""
            rows.append({"record_uid": "U%08d" % i, "step": str(step), "event_ts": event_ts,
                         "type": rng.choice(["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"]),
                         "amount": "%.2f" % rng.uniform(0, 20000),
                         "nameOrig": rng.choice(origins), "nameDest": rng.choice(dests),
                         "isFraud": rng.choice(["0", "1"])})
        with tempfile.TemporaryDirectory() as work:
            tx = os.path.join(work, "tx.csv")
            self._write_tx(tx, rows)
            out = os.path.join(work, "matrix.csv")
            build_matrix(tx, out, os.path.join(work, "spill"), step_max=743)
            # reference: stream the same tx in causal order through the M4 builder
            os.makedirs(os.path.join(work, "spill2"), exist_ok=True)
            ref = CausalFeatureBuilder()
            expected = {}
            for r in iter_time_sorted(tx, os.path.join(work, "spill2"), step_max=743):
                expected[r["record_uid"]] = ref.add(r)
            # compare each matrix row's history columns to the reference
            hi = [MODEL_MATRIX_COLUMNS.index(c) for c in HISTORY_FEATURES]
            with open(out, newline="", encoding="utf-8") as fh:
                rd = csv.reader(fh); header = next(rd)
                self.assertEqual(header, MODEL_MATRIX_COLUMNS)
                n = 0
                for line in rd:
                    uid = line[0]; n += 1
                    self.assertIn(uid, expected)
                    exp = expected[uid]
                    for name, col in zip(HISTORY_FEATURES, hi):
                        got, want = float(line[col]), float(exp[name])
                        self.assertAlmostEqual(got, want, places=4,
                                               msg=f"{uid} {name}: {got} != {want}")
                self.assertEqual(n, len(rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
