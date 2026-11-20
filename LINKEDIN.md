# LinkedIn campaign workflow

The LinkedIn tracker keeps a private campaign ledger for a member profile, daily posts, scheduling receipts, comment drafts, and measured results. Use the operator's private source of editorial policy and existing approvals. Keep draft copy, account settings, Notion content, individual engagement and performance metrics outside this public checkout.

## Draft and schedule

1. Review the owner's strategy. Pick a narrow editorial hypothesis, and tie each draft to a public artifact or evidence. Distinguish measured results from examples. Check every source and show the owner the exact text, destination and proposed time.
2. Initialize from a campaign JSON with `id`, a LinkedIn member-profile URL in `account`, an IANA `timezone`, and ordered `posts` with consecutive local dates. Use [the synthetic example](examples/linkedin-campaign.json) as the template. Set `DB` to a new SQLite file under a private directory.
3. Record the exact batch fingerprint and approval reference only after the owner approves. The fingerprint covers every post and its slot, content and destination. A different draft batch gets a new campaign ID and fresh approval.
4. The report exposes the exact copy and post fingerprint when a slot is ready. Use a connected, authorized scheduler or [LinkedIn's native scheduler](https://www.linkedin.com/help/linkedin/answer/a1347212). Check the account and existing queue before submission. Read back the saved rows by hook and timestamp afterward. A cached queue badge can lag the list. If the calendar labels are inconsistent, use the date field and confirm the displayed timestamp before submitting. Record a receipt only for a verified row. A past scheduled slot without a publication receipt goes to reconciliation.

```sh
python3 linkedin.py --db "$DB" init /private/path/campaign.json
python3 linkedin.py --db "$DB" approve campaign-id --fingerprint "$REVIEWED_HASH" --evidence "$APPROVAL_REFERENCE"
python3 linkedin.py --db "$DB" report campaign-id
python3 linkedin.py --db "$DB" receipt campaign-id /private/path/receipt.json
```

For initial scheduling and publication, receipt fields are `post`, `state` (`scheduled` or `published`), report `fingerprint`, confirmed `account`, `provider`, stable `external_id`, `url`, event `at`, and `verified_at`. Use offset-aware timestamps. For publication, use the post’s LinkedIn permalink and identifier. A feed URL with an activity, share, or UGC post ID or a `/posts/…-activity-…` permalink works. When the native schedule omits a row ID, use an explicitly labeled local key derived from the confirmed profile, timestamp, and fingerprint. Keep the readback evidence with the receipt. Re-importing an identical receipt is safe. The ledger records operator or provider evidence. It cannot verify an external receipt by itself.

## Record a cancellation or reschedule

Use the same `receipt` command after verifying the change in the scheduler. Set `state` to `cancelled` or `rescheduled`, keep the original post `fingerprint` and account, and include the current `schedule_revision` from the report as `previous`. Put the confirmed readback reference in `evidence` and its timestamp in `verified_at`.

- For a cancellation, use the active schedule’s provider, `external_id`, and slot as `at`.
- For a reschedule, use the replacement row’s provider, `external_id`, and new slot as `at`. Obtain fresh owner approval for that exact post and time before changing the scheduler. Put the owner’s approval reference in `approval_evidence` and the hash below in `revised_fingerprint`. Use the same timestamp string in the hash command and the receipt.

```sh
python3 linkedin.py --db "$DB" reschedule-fingerprint campaign-id post-id 2030-01-03T18:30:00+05:30
```

The report retains the original slot in `approved_slot` and the subsequent receipts in `schedule_changes`. The current `slot` and `scheduled` receipt drive publication reconciliation. Cancelled rows have no active schedule.

## Comment review

Use per-post discussion prompts to guide real conversations. Save a reply suggestion only after reading the target and identifying the specific statement or question it addresses. Import a reply object with `id`, `target` (LinkedIn URL), `context`, `draft` and `review_at`. The owner decides whether to send it through LinkedIn. Record manual disposition with the same `id`, `state` (`sent-manually` or `skip`), `reviewed_at` and `evidence`. LinkedIn's [authentic conversation policy](https://news.linkedin.com/2026/authentic-content-and-conversations) prohibits automated commenting.

```sh
python3 linkedin.py --db "$DB" reply campaign-id /private/path/draft-reply.json
python3 linkedin.py --db "$DB" reply-close campaign-id /private/path/disposition.json
```

## Analytics and strategy

On each daily check, reconcile due publications and replies. Capture verified individual-post analytics near 24 hours and 7 days from actual publication. The intake windows are 24–36 hours and 7–8 days. Late snapshots are retained but do not fill missed comparison windows. Use one provider per comparison. For each post and metric, use the earliest known value in the window. The report’s `metric_sources` gives each value used, its timestamp, and its evidence. Preserve inaccessible values as null and differentiate a measured zero from missing evidence. Snapshot fields are `post`, `provider`, `observed_at`, `evidence` and `metrics`. Recognized metrics appear in `linkedin.py`. Count a substantive comment when it contributes a counterexample, concrete implementation detail, or answerable technical question. Attribute qualified inbound only when the connection to the post can be established.

At the weekly review, compare matched-age results by format and angle. Read sample sizes per metric before drawing conclusions. Use substantive comments, saves and qualified inbound as primary measures. Reach and follower trend give context. If fewer than three comparable posts per angle have the primary metric, record `hold` and keep collecting. Otherwise record the evidence and choose one variable to test next. These small descriptive cohorts cannot establish causation. Keep outcome evidence in the ledger and use the existing [architecture loop](ARCHITECTURE.md) for repeated tooling friction.

```sh
python3 linkedin.py --db "$DB" snapshot campaign-id /private/path/metrics.json
python3 linkedin.py --db "$DB" decision campaign-id /private/path/weekly-review.json
```

Weekly record fields are `reviewed_at`, `decision` (`hold`, `continue`, `iterate`), `evidence`, `next_hypothesis` and `success_measure`.
