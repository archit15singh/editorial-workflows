# Validate the local batch before reading production

Trigger: The new architecture loop reviewed the verifier's local and live behavior.
Evidence: A two-post fixture with a missing second build page called the production reader four times for the first post before reporting the local error.
Design: Finish local page, markup, and asset checks first. Pass the validated pages and unique local asset digests to live comparison. Use the same markup checks in both phases.
Decision: Apply the split. Keep the manifest and CLI invocation compatible, and emit passing results after the requested verification finishes.
Verification: The incomplete-build regression now observes zero live requests. Existing stale-copy, stale-markup, and stale-asset checks pass. The three-post Hugo build and its live deployment pass through the CLI.
