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
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:1234567890/",
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

    def test_cancel_and_reschedule_keep_approval_and_history(self):
        self.approve()
        schedule = self.receipt("scheduled")
        linkedin.evidence_receipt(self.db, PLAN, schedule, NOW)
        slot = (BASE + timedelta(days=2)).isoformat()
        change = {**schedule, "state": "rescheduled", "at": slot,
                  "verified_at": (BASE + timedelta(hours=2)).isoformat(),
                  "previous": linkedin.fingerprint(schedule), "evidence": "Planner readback",
                  "approval_evidence": "Owner approved this new time"}
        with self.assertRaisesRegex(ValueError, "revised post fingerprint"):
            linkedin.evidence_receipt(self.db, PLAN, change, NOW)
        change["revised_fingerprint"] = linkedin.fingerprint({**PLAN["posts"][0], "slot": slot})
        linkedin.evidence_receipt(self.db, PLAN, change, NOW)
        row = linkedin.report(self.db, PLAN, BASE + timedelta(days=1))["posts"][0]
        self.assertEqual((row["status"], row["slot"]), ("scheduled", slot))
        self.assertEqual(row["schedule_revision"], linkedin.fingerprint(change))
        cancelled = {**schedule, "state": "cancelled", "at": slot,
                     "verified_at": (BASE + timedelta(hours=3)).isoformat(),
                     "previous": linkedin.fingerprint(change), "evidence": "Removal confirmed"}
        with self.assertRaisesRegex(ValueError, "current schedule revision"):
            linkedin.evidence_receipt(self.db, PLAN, {**cancelled, "previous": change["previous"]}, NOW)
        linkedin.evidence_receipt(self.db, PLAN, cancelled, NOW)
        linkedin.evidence_receipt(self.db, PLAN, change, NOW)
        linkedin.evidence_receipt(self.db, PLAN, cancelled, NOW)
        row = linkedin.report(self.db, PLAN, NOW)["posts"][0]
        self.assertEqual(row["status"], "cancelled")
        self.assertIsNone(row["scheduled"])
        self.assertEqual(row["schedule_changes"], [change, cancelled])
        self.assertEqual(row["approved_slot"], PLAN["posts"][0]["slot"])
        restored = {**change, "previous": linkedin.fingerprint(cancelled),
                    "verified_at": (BASE + timedelta(hours=4)).isoformat()}
        with self.assertRaisesRegex(ValueError, "verified after"):
            linkedin.evidence_receipt(self.db, PLAN, {**restored, "verified_at": change["verified_at"]}, NOW)
        linkedin.evidence_receipt(self.db, PLAN, restored, NOW)
        self.assertEqual(linkedin.report(self.db, PLAN, NOW)["posts"][0]["status"], "reconcile-publication")
        linkedin.evidence_receipt(self.db, PLAN, self.receipt("published"), NOW)
        with self.assertRaisesRegex(ValueError, "no verified publication"):
            linkedin.evidence_receipt(self.db, PLAN, {**cancelled, "previous": linkedin.fingerprint(restored)}, NOW)
        self.assertEqual(linkedin.report(self.db, PLAN, NOW)["posts"][0]["status"], "published")

    def test_publication_requires_a_permalink(self):
        self.approve()
        receipt = self.receipt("published")
        for url in ("https://www.linkedin.com/", "https://www.linkedin.com/in/member/",
                    "https://www.linkedin.com/feed/update/example/",
                    "https://www.linkedin.com.evil.example/feed/update/urn:li:activity:123/"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "LinkedIn post permalink"):
                linkedin.evidence_receipt(self.db, PLAN, {**receipt, "url": url}, NOW)
        for url in (receipt["url"], "https://www.linkedin.com/feed/update/urn%3Ali%3AugcPost%3A123/",
                    "https://linkedin.com/feed/update/urn:li:share:123/",
                    "https://www.linkedin.com/posts/alex_sample-activity-123456789-ABcd?trk=test"):
            with self.subTest(url=url):
                with self.db:
                    linkedin.evidence_receipt(self.db, PLAN, {**receipt, "url": url}, NOW)
                    self.db.execute("DELETE FROM receipts")

    def test_comparisons_use_earliest_known_value_per_metric(self):
        self.approve()
        linkedin.evidence_receipt(self.db, PLAN, self.receipt("published"), NOW)
        for hours, provider, impressions, saves in (
            (24, "native", 200, None), (25, "native", 205, 7),
            (26, "native", 210, 8), (37, "native", 225, 10),
            (24, "other", 50, 0), (168, "native", 600, None),
        ):
            linkedin.record_snapshot(self.db, PLAN, {
                "post": KEY, "provider": provider, "evidence": f"Observation at {hours} hours",
                "observed_at": (BASE + timedelta(hours=hours)).isoformat(),
                "metrics": {"impressions": impressions, "saves": saves},
            }, NOW)
        result = linkedin.report(self.db, PLAN, NOW)
        cohort = {(row["window"], row["provider"]): row["metrics"] for row in result["comparisons"]}
        self.assertEqual(cohort["24h", "native"]["impressions"], {"n": 1, "median": 200})
        self.assertEqual(cohort["24h", "native"]["saves"], {"n": 1, "median": 7})
        self.assertEqual(cohort["24h", "other"]["saves"], {"n": 1, "median": 0})
        self.assertEqual(cohort["7d", "native"]["saves"], {"n": 0, "median": None})
        sources = result["posts"][0]["checks"][0]["metric_sources"]["native"]
        self.assertEqual(sources["saves"], {
            "value": 7, "observed_at": (BASE + timedelta(hours=25)).isoformat(),
            "evidence": "Observation at 25 hours",
        })

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
            slot = "2030-01-03T18:30:00+05:30"
            revised = subprocess.run([*cli, "reschedule-fingerprint", PLAN["id"], KEY, slot],
                                     check=True, capture_output=True, text=True)
            self.assertEqual(revised.stdout.strip(), linkedin.fingerprint({**PLAN["posts"][0], "slot": slot}))


if __name__ == "__main__":
    unittest.main()
