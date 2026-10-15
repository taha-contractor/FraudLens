"""Focused tests for the M5 modelling layer (splits + integrity + metrics).

Small synthetic matrices only — these validate the split/leakage/integrity contract
that gates training, not full-scale performance.
"""

import csv
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from features.matrix import MODEL_MATRIX_COLUMNS  # noqa: E402
from modeling import dataset as ds  # noqa: E402
from modeling.evaluate import best_threshold_by_f1, metrics_at  # noqa: E402


def _write_matrix(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(MODEL_MATRIX_COLUMNS)
        for r in rows:
            w.writerow(r)


def _mk(i, step, ocode, origin, typ, fraud):
    # record_uid, origin, step, type, amount, oldbalance, nameDest, isFraud, +9 history
    hist = [i % 5, 10.0, 1.5, 2.0, 3, 100.0, 2, i % 7, i % 3]
    return [f"U{i:06d}", origin, step, typ, "50.00", "1000.00", f"D{ocode}", fraud] + hist


class SplitIntegrityTests(unittest.TestCase):
    def _data(self, tmp):
        rows = []
        k = 0
        for step in range(1, 744):
            for o in range(4):
                origin = "original" if (step + o) % 3 else "generated"
                typ = ["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"][o]
                fraud = "1" if (k % 40 == 0) else "0"
                rows.append(_mk(k, step, o, origin, typ, fraud))
                k += 1
        path = os.path.join(tmp, "m.csv")
        _write_matrix(path, rows)
        data = ds.load_matrix(path, n_rows=len(rows))
        ds.build_splits(data, train_max=500, val_max=620, holdout_seed=42, holdout_frac=0.2)
        return data

    def test_no_leakage_in_feature_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._data(tmp)
            self.assertEqual(ds.audit.scan_forbidden("pre", data["feature_columns"]), [])

    def test_splits_disjoint_temporal_and_unseen(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._data(tmp)
            rep = ds.integrity_report(data)
            self.assertEqual(rep["issues"], [], msg=str(rep["issues"]))
            a, st = data["assign"], data["step"]
            # every row gets exactly one label
            self.assertTrue(set(a.tolist()) <= {"train", "val", "test", "unseen"})
            # temporal order within the seen population: train/val steps < test steps
            self.assertLess(st[a == "train"].max(), st[a == "test"].min())
            self.assertLess(st[a == "val"].max(), st[a == "test"].min())
            # unseen destinations must not appear in train
            dest, unseen = data["dest_codes"], data["unseen_mask"]
            train_dest = set(dest[a == "train"].tolist())
            self.assertEqual(train_dest & set(dest[unseen].tolist()), set())

    def test_all_rows_assigned_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._data(tmp)
            counts = {k: len(v) for k, v in data["split_index"].items()}
            self.assertEqual(sum(counts.values()), data["n"])

    def test_unseen_holdout_populated_and_no_stranded_rows(self):
        # Regression: build_splits used a fixed-width string label too narrow for
        # "unseen" (6 chars), silently truncating it and stranding every held-out
        # row outside all four splits. Use many destinations so the 20%-fraction
        # account-level holdout is guaranteed non-empty.
        rows = []
        k = 0
        for step in range(1, 400):
            for o in range(20):                      # 20 distinct destinations
                typ = ["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"][o % 5]
                fraud = "1" if (k % 30 == 0) else "0"
                rows.append(_mk(k, step, o, "generated", typ, fraud))
                k += 1
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.csv")
            _write_matrix(path, rows)
            data = ds.load_matrix(path, n_rows=len(rows))
            ds.build_splits(data, train_max=250, val_max=320, holdout_seed=42,
                            holdout_frac=0.2)
            counts = {lab: len(ix) for lab, ix in data["split_index"].items()}
            self.assertGreater(counts["unseen"], 0, msg="unseen holdout must be populated")
            # no row may be stranded in an unlabelled/truncated bucket
            self.assertEqual(sum(counts.values()), data["n"])
            self.assertTrue(set(data["assign"].tolist()) <= {"train", "val", "test", "unseen"})
            # integrity report must agree that the holdout never touches train
            self.assertEqual(ds.integrity_report(data)["issues"], [])

    def test_threshold_and_metrics_shapes(self):
        y = np.array([0] * 95 + [1] * 5)
        prob = np.array([0.05] * 95 + [0.9] * 5)
        thr, f1 = best_threshold_by_f1(y, prob)
        self.assertGreater(f1, 0.5)
        m = metrics_at(y, prob, thr)
        for key in ("precision", "recall", "f1", "false_positives", "false_negatives"):
            self.assertIn(key, m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
