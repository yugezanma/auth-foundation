"""spec/vectors/ の判定テストをすべて Python 版で流す。"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "python"))

from auth_foundation import AUDIT_ACTIONS, __version__  # noqa: E402
from auth_foundation.audit import PATTERNS  # noqa: E402
from auth_foundation.verify_vendor import run_case  # noqa: E402

VECTORS = os.path.join(ROOT, "spec", "vectors")


class VectorTest(unittest.TestCase):
    def test_vectors(self):
        names = sorted(n for n in os.listdir(VECTORS) if n.endswith(".json"))
        self.assertGreater(len(names), 0)
        total = 0
        for n in names:
            with open(os.path.join(VECTORS, n), encoding="utf-8") as f:
                doc = json.load(f)
            for case in doc["cases"]:
                total += 1
                with self.subTest(file=n, case=case.get("name")):
                    self.assertIsNone(run_case(doc, case))
        self.assertGreater(total, 400)


class ConsistencyTest(unittest.TestCase):
    def test_version_matches_file(self):
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), __version__)

    def test_audit_actions_match_spec(self):
        with open(os.path.join(ROOT, "spec", "audit-actions.json"), encoding="utf-8") as f:
            spec = json.load(f)
        self.assertEqual([(a["name"], a["required"], a["retention"], a["reserved"]) for a in spec["actions"]],
                         list(AUDIT_ACTIONS))
        self.assertEqual([(p["pattern"], p["required"], p["retention"]) for p in spec["patterns"]], list(PATTERNS))

    def test_sync_audit_actions_is_up_to_date(self):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_audit_actions.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
