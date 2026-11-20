from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import linkedin

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "examples/linkedin-campaign.json").read_text())
BASE = datetime(2030, 1, 1, 13, tzinfo=timezone.utc)
NOW = BASE + timedelta(days=10)
KEY = PLAN["posts"][0]["id"]
ACCOUNT = PLAN["account"]


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(linkedin.SCHEMA)
        self.db.execute("INSERT INTO campaign VALUES (?, ?)", (PLAN["id"], linkedin.json_text(PLAN)))

    def approve(self):
        self.db.execute("INSERT INTO approvals VALUES (?, ?, ?)",
                        (PLAN["id"], linkedin.fingerprint(PLAN), "owner review"))

    def receipt(self, state):
        return {"post": KEY, "state": state, "fingerprint": linkedin.fingerprint(PLAN["posts"][0]),
                "provider": "linkedin-native", "account": ACCOUNT, "external_id": "test-id",
                "url": "https://www.linkedin.com/feed/update/example/",
                "at": BASE.isoformat(), "verified_at": min(NOW, BASE + timedelta(hours=1)).isoformat()}

    def test_approval_and_exact_destination_gate_schedule(self):
        self.assertEqual(linkedin.report(self.db, PLAN, BASE)["posts"][0]["status"], "draft")
        with self.assertRaisesRegex(ValueError, "approval"):
            linkedin.evidence_receipt(self.db, PLAN, self.receipt("scheduled"), NOW)
        self.approve()
        receipt = self.receipt("scheduled")
        with self.assertRaisesRegex(ValueError, "account differs"):
            linkedin.evidence_receipt(self.db, PLAN, {**receipt, "account": "wrong"}, NOW)
        with self.assertRaisesRegex(ValueError, "approved slot"):
            linkedin.evidence_receipt(self.db, PLAN, {**receipt, "at": NOW.isoformat()}, NOW)
        linkedin.evidence_receipt(self.db, PLAN, receipt, NOW)
        linkedin.evidence_receipt(self.db, PLAN, receipt, NOW)
        self.assertEqual(linkedin.report(self.db, PLAN, NOW)["posts"][0]["status"], "reconcile-publication")

    def test_only_comparable_observations_count_and_null_is_not_zero(self):
        self.approve()
        linkedin.evidence_receipt(self.db, PLAN, self.receipt("published"), NOW)
        start = {"post": KEY, "provider": "linkedin-native", "evidence": "observed",
                 "metrics": {"saves": None, "substantive_comments": 0}}
        for hours in (23, 35, 41):
            linkedin.record_snapshot(self.db, PLAN, {
                **start, "observed_at": (BASE + timedelta(hours=hours)).isoformat(),
            }, NOW)
        result = linkedin.report(self.db, PLAN, NOW)
        self.assertEqual([x["state"] for x in result["posts"][0]["checks"]], ["observed", "missed"])
        metrics = result["comparisons"][0]["metrics"]
        self.assertEqual(metrics["saves"], {"n": 0, "median": None})
        self.assertEqual(metrics["substantive_comments"], {"n": 1, "median": 0})

    def test_no_analytics_before_publication_and_replies_stay_manual(self):
        with self.assertRaisesRegex(ValueError, "publication"):
            linkedin.record_snapshot(self.db, PLAN, {"post": KEY}, NOW)
        reply = {"id": "reply-1", "target": "https://www.linkedin.com/feed/update/example/",
                 "context": "Technical question", "draft": "A specific answer", "review_at": BASE.isoformat()}
        linkedin.record_reply(self.db, PLAN["id"], reply)
        self.assertTrue(linkedin.report(self.db, PLAN, NOW)["reply_review"][0]["due"])
        linkedin.close_reply(self.db, PLAN["id"], {
            "id": "reply-1", "state": "skip", "reviewed_at": NOW.isoformat(), "evidence": "Owner skipped",
        }, NOW)
        self.assertFalse(linkedin.report(self.db, PLAN, NOW)["reply_review"][0]["due"])

    def test_cli_can_open_example_without_approving_it(self):
        with TemporaryDirectory() as directory:
            cli = [sys.executable, str(ROOT / "linkedin.py"), "--db", str(Path(directory) / "data.db")]
            subprocess.run([*cli, "init", str(ROOT / "examples/linkedin-campaign.json")],
                           check=True, capture_output=True)
            proc = subprocess.run([*cli, "report", PLAN["id"]], check=True, capture_output=True)
            self.assertFalse(json.loads(proc.stdout)["approved"])


if __name__ == "__main__":
    unittest.main()
