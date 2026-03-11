#!/usr/bin/env python3
import csv
import os
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.getenv("RUN_FUSION_REGRESSION") == "1",
    "Set RUN_FUSION_REGRESSION=1 to run CSV regression checks.",
)
class TestFusionRegressionFromCsv(unittest.TestCase):
    def test_regression_runner_outputs_match(self):
        repo_root = Path(__file__).resolve().parents[1]
        runner = repo_root / "tests" / "run_fusion_regression.py"

        # Run the generator first so assertions use fresh artifacts.
        completed = subprocess.run(
            [sys.executable, str(runner)],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"Runner failed:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
        )

        actual_csv = repo_root / "tests" / "artifacts" / "fusion_testcase_results.csv"
        compare_csv = repo_root / "tests" / "artifacts" / "fusion_testcase_intended_vs_actual.csv"

        with actual_csv.open("r", newline="", encoding="utf-8") as f:
            actual_rows = list(csv.DictReader(f))
        self.assertTrue(actual_rows, "No rows found in fusion_testcase_results.csv")

        failed_actual = [r for r in actual_rows if (r.get("Match?") or "").strip().upper() == "FAIL"]
        self.assertEqual(
            len(failed_actual),
            0,
            msg=f"Actual-vs-provided mismatches: {[r.get('Test Case') for r in failed_actual]}",
        )

        with compare_csv.open("r", newline="", encoding="utf-8") as f:
            compare_rows = list(csv.DictReader(f))
        self.assertTrue(compare_rows, "No rows found in fusion_testcase_intended_vs_actual.csv")

        failed_intended = [
            r
            for r in compare_rows
            if (r.get("Intended vs Actual") or "").strip().upper() == "FAIL"
        ]
        self.assertEqual(
            len(failed_intended),
            0,
            msg=f"Intended-vs-actual mismatches: {[r.get('Test Case') for r in failed_intended]}",
        )


if __name__ == "__main__":
    unittest.main()
