"""Tests for the M1 read-only PaySim loader.

Run from the repo root (with the ML source on PYTHONPATH), using the project Python env:
    $env:PYTHONPATH="ml/src"; python -m unittest discover -s ml/tests -t ml/tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "ml" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data import origindata  # noqa: E402

RAW = REPO_ROOT / "ml" / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"


def _fixture_df():
    return pd.DataFrame({
        "step": [1, 1, 2, 2],
        "type": ["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN"],
        "amount": [10.0, 250.0, 999.0, 50.0],
        "nameOrig": ["C1", "C2", "C3", "C4"],
        "oldbalanceOrg": [100.0, 500.0, 999.0, 0.0],
        "newbalanceOrig": [90.0, 250.0, 0.0, 50.0],
        "nameDest": ["M1", "C5", "C6", "C7"],
        "oldbalanceDest": [0.0, 0.0, 0.0, 0.0],
        "newbalanceDest": [0.0, 250.0, 999.0, 0.0],
        "isFraud": [0, 1, 1, 0],
        "isFlaggedFraud": [0, 0, 0, 0],
    })


class FixtureTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        _fixture_df().to_csv(self.path, index=False)

    def tearDown(self):
        os.remove(self.path)

    def test_schema_validates_on_good_fixture(self):
        origindata.validate_schema(pd.read_csv(self.path))  # no raise

    def test_column_order_mismatch_raises(self):
        df = pd.read_csv(self.path)
        bad = df.drop(columns=["step"])
        with self.assertRaises(origindata.SchemaError):
            origindata.validate_schema(bad)

    def test_profile_counts_labels_and_types(self):
        prof = origindata.profile_source(self.path, chunksize=2, verify_checksum=False)
        self.assertEqual(prof["rows"], 4)
        self.assertEqual(prof["fraud"]["count"], 2)
        self.assertEqual(prof["missing_values"], 0)
        self.assertEqual(prof["transaction_type_counts"]["PAYMENT"], 1)
        # fraud lives only in TRANSFER + CASH_OUT in this fixture
        self.assertEqual(set(prof["fraud_by_type"]), {"TRANSFER", "CASH_OUT"})
        self.assertEqual(prof["invalid_transaction_types"], [])

    def test_profile_detects_invalid_type(self):
        df = _fixture_df()
        df.loc[0, "type"] = "WIRE"
        df.to_csv(self.path, index=False)
        prof = origindata.profile_source(self.path, chunksize=2, verify_checksum=False)
        self.assertIn("WIRE", prof["invalid_transaction_types"])


class RealSourceTests(unittest.TestCase):
    @unittest.skipUnless(RAW.exists(), "PaySim source file not present")
    def test_checksum_and_size_match_expected(self):
        fp = origindata.verify_integrity(str(RAW))
        self.assertEqual(fp["sha256"], origindata.EXPECTED_SHA256)
        self.assertEqual(fp["size_bytes"], origindata.EXPECTED_SIZE_BYTES)

    @unittest.skipUnless(RAW.exists(), "PaySim source file not present")
    def test_reads_do_not_modify_source(self):
        before = origindata.file_fingerprint(str(RAW))
        origindata.load_first_chunk(str(RAW), n=5000)
        after = origindata.file_fingerprint(str(RAW))
        self.assertEqual(before["sha256"], after["sha256"])
        self.assertEqual(before["size_bytes"], after["size_bytes"])

    @unittest.skipUnless(RAW.exists(), "PaySim source file not present")
    def test_first_chunk_schema_ok(self):
        df = origindata.load_first_chunk(str(RAW), n=1000)
        self.assertEqual(list(df.columns), origindata.EXPECTED_COLUMNS)


if __name__ == "__main__":
    unittest.main()
