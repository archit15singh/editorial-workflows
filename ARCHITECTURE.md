# Architecture improvement loop

Run a pass before opening or updating a harness PR that changes production Python or GitHub workflows. During an editorial run, also start a pass if you see a manual workaround twice, need a second way to supply the same input, or find verification relying on the wrong layer. An ordinary draft or figure change needs no architecture pass.

## Run a pass

1. **Detect the trigger.** From the harness repository root, run `python3 scripts/architecture_review.py`. It compares the working tree with the merge base of `origin/main` and lists changed code and workflows. For evidence a diff cannot see, add `--signal "describe what happened"`.
2. **Reproduce the friction.** Use a small case and record what went wrong, which callers learn too much about implementation, and which module or test ought to own the behavior. Bug fixes should have a failing regression check when feasible.
3. **Choose one improvement.** Compare keeping the current design with the smallest change that consolidates the invariant or makes it easier to test. Preserve CLI behavior and manifest compatibility. Apply one scoped improvement when the reproduction supports it and the current task authorizes harness edits. Defer larger changes with the evidence and a condition for revisiting them.
4. **Verify and record.** Run the regression and the full unit suite. For verifier changes, run the CLI against the relevant Hugo build and a matching live release when available. Add one short Markdown file in [architecture/reviews/](architecture/reviews/) with the fields `Trigger`, `Evidence`, `Design`, `Decision`, and `Verification`, each with a nonempty value on the same line. Keep private details out of public records. If the current task only authorizes blog edits, record the finding in that run's notes for a future harness change.
5. **Close the pass.** Rerun the detector with the same base and signal. Stop once the regression passes or the decision to keep or defer the change is recorded. Reopen on a new trigger or new evidence.

GitHub Actions checks for a new review record on code and workflow PRs. That check verifies the record is present and shaped correctly. The agent or reviewer evaluates the design and the evidence.
