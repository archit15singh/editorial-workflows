#!/usr/bin/env python3
"""Track a LinkedIn campaign, approved scheduling handoffs and measured outcomes."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from sqlite3 import IntegrityError, connect
from statistics import median
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

METRICS = ("impressions", "reactions", "comments", "substantive_comments",
           "reposts", "saves", "qualified_inbound")
WINDOWS = {"24h": (24, 12), "7d": (168, 24)}
POST_PATH = re.compile(
    r"/(?:feed/update/urn:li:(?:activity|ugcPost|share):[0-9]+"
    r"|posts/[^/?#\s]+-activity-[0-9]+(?:-[A-Za-z0-9_-]+)?)/?"
)
SCHEDULE_CHANGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule_changes (
    campaign TEXT NOT NULL REFERENCES campaign(id), post TEXT NOT NULL,
    verified TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (campaign, post, verified)
)
"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    campaign TEXT PRIMARY KEY REFERENCES campaign(id), fingerprint TEXT NOT NULL,
    evidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
    campaign TEXT NOT NULL REFERENCES campaign(id), post TEXT NOT NULL,
    state TEXT NOT NULL, provider TEXT NOT NULL, account TEXT NOT NULL, external_id TEXT NOT NULL,
    payload TEXT NOT NULL, PRIMARY KEY (campaign, post, state),
    UNIQUE (provider, account, external_id, state)
);
CREATE TABLE IF NOT EXISTS snapshots (
    campaign TEXT NOT NULL REFERENCES campaign(id), post TEXT NOT NULL,
    provider TEXT NOT NULL, observed TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (campaign, post, provider, observed)
);
CREATE TABLE IF NOT EXISTS replies (
    campaign TEXT NOT NULL REFERENCES campaign(id), id TEXT NOT NULL,
    payload TEXT NOT NULL, PRIMARY KEY (campaign, id)
);
CREATE TABLE IF NOT EXISTS reply_outcomes (
    campaign TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (campaign, id), FOREIGN KEY (campaign, id) REFERENCES replies(campaign, id)
);
CREATE TABLE IF NOT EXISTS decisions (
    campaign TEXT NOT NULL REFERENCES campaign(id), review TEXT NOT NULL,
    payload TEXT NOT NULL, PRIMARY KEY (campaign, review)
);
"""


def required(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError(f"timestamp needs an explicit offset: {value}")
    return parsed


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fingerprint(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def https_url(value, field, linkedin_only=False):
    parsed = urlsplit(required(value, field))
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or (linkedin_only and not (parsed.hostname == "linkedin.com"
                                       or parsed.hostname.endswith(".linkedin.com")))):
        raise ValueError(f"invalid {field}")
    return value


def validate_plan(plan):
    required(plan["id"], "campaign ID")
    https_url(plan["account"], "personal profile", linkedin_only=True)
    if not urlsplit(plan["account"]).path.startswith("/in/"):
        raise ValueError("campaign account must be a LinkedIn member profile")
    zone = ZoneInfo(plan["timezone"])
    posts = plan["posts"]
    if not posts:
        raise ValueError("campaign is empty")
    ids = set()
    dates = []
    for post in posts:
        key = required(post["id"], "post ID")
        if key in ids:
            raise ValueError(f"duplicate post: {key}")
        ids.add(key)
        slot = instant(post["slot"])
        if slot.utcoffset() != slot.astimezone(zone).utcoffset():
            raise ValueError(f"{key}: timestamp offset disagrees with {plan['timezone']}")
        dates.append(slot.astimezone(zone).date())
        for field in ("pillar", "format", "angle", "text", "discussion"):
            required(post[field], field)
        if not post["sources"]:
            raise ValueError(f"{key}: missing sources")
        for source in post["sources"]:
            https_url(source, "source")
    if any(b - a != timedelta(days=1) for a, b in zip(dates, dates[1:])):
        raise ValueError("expected one post per consecutive local date")


def immutable_insert(db, table, columns, key, payload):
    # Identifiers come from the fixed internal call sites.
    predicate = " AND ".join(f"{name} = ?" for name in columns)
    current = db.execute(f"SELECT payload FROM {table} WHERE {predicate}", key).fetchone()
    if current:
        if current[0] != payload:
            raise ValueError(f"conflicting {table} record for {key}")
        return
    fields = ", ".join([*columns, "payload"])
    marks = ", ".join("?" for _ in range(len(key) + 1))
    db.execute(f"INSERT INTO {table} ({fields}) VALUES ({marks})", (*key, payload))


def load_campaign(db, campaign):
    row = db.execute("SELECT payload FROM campaign WHERE id = ?", (campaign,)).fetchone()
    if not row:
        raise ValueError(f"unknown campaign: {campaign}")
    return json.loads(row[0])


def find_post(plan, post_id):
    post = next((post for post in plan["posts"] if post["id"] == post_id), None)
    if post is None:
        raise ValueError(f"unknown campaign post: {post_id}")
    return post


def load_receipts(db, campaign):
    rows = db.execute("SELECT post, state, payload FROM receipts WHERE campaign = ?", (campaign,))
    return {(post, state): json.loads(payload) for post, state, payload in rows}


def load_schedule_changes(db, campaign):
    changes = defaultdict(list)
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schedule_changes'").fetchone():
        for post, payload in db.execute(
            "SELECT post, payload FROM schedule_changes WHERE campaign = ? ORDER BY verified", (campaign,)
        ):
            changes[post].append(json.loads(payload))
    return changes


def record_schedule_change(db, plan, post, item, receipts, recorded):
    campaign, post_id = plan["id"], post["id"]
    changes = load_schedule_changes(db, campaign)[post_id]
    if item in changes:
        return
    current = changes[-1] if changes else receipts.get((post_id, "scheduled"))
    if current is None or (post_id, "published") in receipts:
        raise ValueError("schedule change requires an existing schedule and no verified publication")
    if item.get("previous") != fingerprint(current):
        raise ValueError("schedule change must reference the current schedule revision")
    if recorded <= instant(current["verified_at"]):
        raise ValueError("schedule change must be verified after the prior revision")
    required(item["evidence"], "schedule change evidence")
    if item["state"] == "cancelled":
        if (current["state"] == "cancelled" or instant(item["at"]) != instant(current["at"])
                or any(item[field] != current[field] for field in ("provider", "external_id"))):
            raise ValueError("cancellation must match the active provider, receipt identifier and slot")
    else:
        if current["state"] != "cancelled" and instant(item["at"]) == instant(current["at"]):
            raise ValueError("reschedule needs a different slot or a previously cancelled schedule")
        if item.get("revised_fingerprint") != fingerprint({**post, "slot": item["at"]}):
            raise ValueError("reschedule requires the revised post fingerprint")
        required(item["approval_evidence"], "owner approval for the revised post and slot")
    # Older ledgers only need this table when an operator records the first change.
    db.execute(SCHEDULE_CHANGE_SCHEMA)
    db.execute("INSERT INTO schedule_changes VALUES (?, ?, ?, ?)",
               (campaign, post_id, recorded.astimezone(timezone.utc).isoformat(), json_text(item)))


def approved(db, plan):
    row = db.execute("SELECT fingerprint FROM approvals WHERE campaign = ?", (plan["id"],)).fetchone()
    return row is not None and row[0] == fingerprint(plan)


def evidence_receipt(db, plan, item, now):
    campaign, post_id, state = plan["id"], item["post"], item["state"]
    post = find_post(plan, post_id)
    if state not in ("scheduled", "published", "cancelled", "rescheduled"):
        raise ValueError("unsupported receipt state")
    if not approved(db, plan) or item["fingerprint"] != fingerprint(post):
        raise ValueError("receipt requires approval and the exact post fingerprint")
    provider = required(item["provider"], "provider")
    if item["account"] != plan["account"]:
        raise ValueError("receipt account differs from approved profile")
    external_id = required(item["external_id"], "provider receipt identifier")
    receipts = load_receipts(db, campaign)
    old = receipts.get((post_id, state))
    if old is not None:
        if old != item:
            raise ValueError("receipt conflicts with existing verified state")
        return
    if state == "published":
        url = https_url(item["url"], "LinkedIn post permalink", linkedin_only=True)
        parsed = urlsplit(url)
        if (parsed.username is not None or parsed.port not in (None, 443)
                or not POST_PATH.fullmatch(unquote(parsed.path))):
            raise ValueError("invalid LinkedIn post permalink")
    else:
        https_url(item["url"], "receipt URL")
    event = instant(item["at"])
    recorded = instant(item["verified_at"])
    if recorded > now:
        raise ValueError("receipt verification is in the future")
    if state in ("cancelled", "rescheduled"):
        record_schedule_change(db, plan, post, item, receipts, recorded)
        return
    if state == "scheduled" and event != instant(post["slot"]):
        raise ValueError("verified scheduled instant differs from approved slot")
    if state == "published" and event > recorded:
        raise ValueError("published instant is later than its observation")
    db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?)",
               (campaign, post_id, state, provider, item["account"], external_id, json_text(item)))


def record_snapshot(db, plan, item, now):
    campaign, post_id = plan["id"], item["post"]
    publication = load_receipts(db, campaign).get((post_id, "published"))
    if publication is None:
        raise ValueError("analytics needs a verified publication receipt")
    provider = required(item["provider"], "metrics provider")
    required(item["evidence"], "metrics evidence")
    observed = instant(item["observed_at"])
    if not instant(publication["at"]) <= observed <= now:
        raise ValueError("observation must follow publication and cannot be in the future")
    values = item["metrics"]
    if not values or set(values) - set(METRICS):
        raise ValueError("invalid or empty metrics")
    if any(value is not None and (type(value) is not int or value < 0) for value in values.values()):
        raise ValueError("metrics are nonnegative integers or null")
    total, substantive = values.get("comments"), values.get("substantive_comments")
    if total is not None and substantive is not None and substantive > total:
        raise ValueError("substantive comments cannot exceed total comments")
    immutable_insert(db, "snapshots", ("campaign", "post", "provider", "observed"),
                     (campaign, post_id, provider, observed.astimezone(timezone.utc).isoformat()),
                     json_text({**item, "observed_at": observed.astimezone(timezone.utc).isoformat()}))


def record_reply(db, campaign, item):
    reply_id = required(item["id"], "reply key")
    https_url(item["target"], "LinkedIn target", linkedin_only=True)
    for field in ("context", "draft"):
        required(item[field], field)
    instant(item["review_at"])
    immutable_insert(db, "replies", ("campaign", "id"), (campaign, reply_id), json_text(item))


def close_reply(db, campaign, item, now):
    if item["state"] not in {"sent-manually", "skip"} or instant(item["reviewed_at"]) > now:
        raise ValueError("record a completed manual reply decision")
    required(item["evidence"], "reply decision evidence")
    immutable_insert(db, "reply_outcomes", ("campaign", "id"),
                     (campaign, item["id"]), json_text(item))


def record_decision(db, campaign, item, now):
    review = instant(item["reviewed_at"]).astimezone(timezone.utc)
    if review > now:
        raise ValueError("review cannot be in the future")
    if item["decision"] not in {"hold", "continue", "iterate"}:
        raise ValueError("invalid decision")
    for field in ("evidence", "next_hypothesis", "success_measure"):
        required(item[field], field)
    immutable_insert(db, "decisions", ("campaign", "review"),
                     (campaign, review.isoformat()), json_text(item))


def report(db, plan, now):
    campaign = plan["id"]
    approval = approved(db, plan)
    receipts = load_receipts(db, campaign)
    schedule_changes = load_schedule_changes(db, campaign)
    grouped = defaultdict(list)
    for post_id, provider, raw in db.execute(
        "SELECT post, provider, payload FROM snapshots WHERE campaign = ?", (campaign,)
    ):
        grouped[post_id, provider].append(json.loads(raw))
    scores = defaultdict(list)
    rows = []
    for post in plan["posts"]:
        key = post["id"]
        publication = receipts.get((key, "published"))
        changes = schedule_changes[key]
        revision = changes[-1] if changes else receipts.get((key, "scheduled"))
        cancelled = revision is not None and revision["state"] == "cancelled"
        schedule = None if cancelled else revision
        slot = revision["at"] if changes else post["slot"]
        row = {"id": key, "slot": slot, "fingerprint": fingerprint(post),
               "hook": post["text"].splitlines()[0], "pillar": post["pillar"],
               "discussion": post["discussion"], "status": "draft", "checks": [],
               "scheduled": schedule, "published": publication}
        if revision:
            row["schedule_revision"] = fingerprint(revision)
        if changes:
            row.update(approved_slot=post["slot"], schedule_changes=changes)
        if publication:
            row["status"] = "published"
            start = instant(publication["at"])
            for label, (hours, grace) in WINDOWS.items():
                due = start + timedelta(hours=hours)
                end = due + timedelta(hours=grace)
                observed = {}
                metric_sources = {}
                for (post_id, provider), observations in grouped.items():
                    if post_id != key:
                        continue
                    options = sorted((x for x in observations if due <= instant(x["observed_at"]) <= end),
                                     key=lambda x: instant(x["observed_at"]))
                    if not options:
                        continue
                    observed[provider] = options[0]
                    values = {}
                    sources = {}
                    for snapshot in options:
                        for metric, value in snapshot["metrics"].items():
                            if value is not None and metric not in values:
                                values[metric] = value
                                sources[metric] = {"value": value, "observed_at": snapshot["observed_at"],
                                                   "evidence": snapshot["evidence"]}
                    metric_sources[provider] = sources
                    scores[label, provider, post["format"], post["angle"]].append(values)
                state = ("observed" if observed else "pending" if now < due
                         else "due" if now <= end else "missed")
                row["checks"].append({"window": label, "state": state, "due_at": due.isoformat(),
                                      "closes_at": end.isoformat(), "observations": observed,
                                      "metric_sources": metric_sources})
        elif cancelled:
            row["status"] = "cancelled"
        elif schedule:
            row["status"] = "reconcile-publication" if now >= instant(slot) else "scheduled"
        elif approval:
            row["status"] = "missed-slot" if now >= instant(post["slot"]) else "ready-to-schedule"
            if row["status"] == "ready-to-schedule":
                row["text"] = post["text"]
        rows.append(row)

    comparisons = []
    for (window, provider, fmt, angle), values in sorted(scores.items()):
        metrics = {}
        for metric in METRICS:
            known = [item[metric] for item in values if item.get(metric) is not None]
            metrics[metric] = {"n": len(known), "median": median(known) if known else None}
        comparisons.append({"window": window, "provider": provider, "format": fmt,
                            "angle": angle, "posts": len(values), "metrics": metrics})
    queue = [json.loads(raw) for (raw,) in db.execute(
        "SELECT payload FROM replies WHERE campaign = ? ORDER BY id", (campaign,))]
    outcomes = {key: json.loads(raw) for key, raw in db.execute(
        "SELECT id, payload FROM reply_outcomes WHERE campaign = ?", (campaign,))}
    queue = [{**reply, "outcome": outcomes.get(reply["id"]),
              "due": reply["id"] not in outcomes and instant(reply["review_at"]) <= now}
             for reply in queue]
    decisions = [json.loads(raw) for (raw,) in db.execute(
        "SELECT payload FROM decisions WHERE campaign = ? ORDER BY review", (campaign,))]
    return {"campaign": campaign, "account": plan["account"], "approved": approval, "fingerprint": fingerprint(plan),
            "posts": rows, "reply_review": queue, "comparisons": comparisons,
            "strategy_log": decisions, "strategy_guidance": (
                "Compare same-age snapshots from the same provider and format. Use substantive "
                "comments, saves and qualified inbound ahead of reach. Report missing data and "
                "sample size. Treat the comparison as descriptive and change one variable next time."
            )}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="private campaign database")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("plan", type=Path)
    approve = sub.add_parser("approve")
    approve.add_argument("campaign")
    approve.add_argument("--fingerprint", required=True)
    approve.add_argument("--evidence", required=True)
    reschedule = sub.add_parser("reschedule-fingerprint", help="hash the exact post and proposed new slot")
    reschedule.add_argument("campaign")
    reschedule.add_argument("post")
    reschedule.add_argument("slot")
    for name in ("receipt", "snapshot", "reply", "reply-close", "decision", "report"):
        cmd = sub.add_parser(name)
        cmd.add_argument("campaign")
        if name != "report":
            cmd.add_argument("input", type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        if args.command != "init" and not args.db.is_file():
            raise ValueError("private database does not exist; run init")
        with connect(args.db) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if args.command == "init":
                db.executescript(SCHEMA)
            read_only = args.command in ("report", "reschedule-fingerprint")
            db.execute("BEGIN" if read_only else "BEGIN IMMEDIATE")
            if args.command == "init":
                plan = json.loads(args.plan.read_text())
                validate_plan(plan)
                immutable_insert(db, "campaign", ("id",), (plan["id"],), json_text(plan))
                print(fingerprint(plan))
                return
            plan = load_campaign(db, args.campaign)
            if args.command == "report":
                print(json.dumps(report(db, plan, now), ensure_ascii=False, indent=2))
                return
            if args.command == "reschedule-fingerprint":
                instant(args.slot)
                print(fingerprint({**find_post(plan, args.post), "slot": args.slot}))
                return
            if args.command == "approve":
                required(args.evidence, "owner approval evidence")
                if args.fingerprint != fingerprint(plan):
                    raise ValueError("approval fingerprint differs from reviewed campaign")
                db.execute("INSERT OR IGNORE INTO approvals VALUES (?, ?, ?)",
                           (args.campaign, args.fingerprint, args.evidence))
                return
            item = json.loads(args.input.read_text())
            if args.command == "receipt":
                evidence_receipt(db, plan, item, now)
            elif args.command == "snapshot":
                record_snapshot(db, plan, item, now)
            elif args.command == "reply":
                record_reply(db, args.campaign, item)
            elif args.command == "reply-close":
                close_reply(db, args.campaign, item, now)
            else:
                record_decision(db, args.campaign, item, now)
    except (ValueError, KeyError, OSError, TypeError, IntegrityError) as error:
        parser.exit(1, f"FAIL {error}\n")


if __name__ == "__main__":
    main()
