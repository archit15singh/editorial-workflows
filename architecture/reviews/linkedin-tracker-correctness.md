# LinkedIn receipts and per-metric observations

Trigger: Production Python changes after an audit of the receipt and analytics boundaries.
Evidence: The old ledger rejected cancellations and later slots, accepted the LinkedIn homepage as publication evidence, and hid saves reported in a second in-window snapshot.
Design: Store schedule changes as append-only receipts linked to the current revision. Validate post permalink shape on new publication receipts. Choose the earliest known observation for each post, provider, window and metric.
Decision: Keep the original plan, approval and receipts intact. Use an optional SQLite table for revisions and preserve the existing report fields while adding per-metric evidence.
Verification: All 17 tests pass. A read-only copy of the existing campaign reports all 14 approved posts with the legacy fields preserved and no database writes.
