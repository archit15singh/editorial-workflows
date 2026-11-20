# Keep LinkedIn campaign state independent of providers

Trigger: The editorial harness needs a recurring LinkedIn tracker, while the connected scheduler has no LinkedIn profile.
Evidence: A planner slot, a verified scheduled row, and an observed publication describe different states. Campaign analytics need the actual publication instant, and retrying without verifying the queue can double-schedule.
Design: Keep account-bound approval, receipts, snapshots, and manual reply disposition in one private ledger. Use provider or operator evidence at intake. Compare snapshots at the same age and with the same provider.
Decision: Add the ledger and a native scheduling handoff. Defer a provider integration until a connected supported interface exists and gives reliable receipts.
Verification: Unit and CLI checks exercise exact approval and destination, idempotent receipts, publication reconciliation, missing versus zero metrics, and manual reply disposition.
