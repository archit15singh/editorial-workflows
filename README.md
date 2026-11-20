# Editorial Workflows

Tools for verifying Hugo posts and tracking LinkedIn schedules, approvals, and results.

Use Python 3.10 or newer. The blog workflow also uses Git and Hugo, plus the destination repository’s release process.

## Blog publishing

Generate a goal for a research and writing agent, then verify the rendered posts and assets before and after deployment. Start with [the editorial workflow](WORKFLOW.md).

```sh
python3 harness.py goal examples/archit-profile.json --count 3
```

Copy the generated goal into a goal-capable agent session rooted here or provide it to your editor. Add `--publish` for a batch with explicit permission to push and merge on the target blog. The CLI prints the prompt. The agent works through [the editorial run](WORKFLOW.md).

With a signed-in Codex CLI, you can also hand off a local batch from this checkout. Use a dedicated writable directory containing the blog checkout and room for its linked worktree. The agent needs primary-source web access for the research step.

```sh
python3 harness.py goal examples/archit-profile.json --count 3 \
  | codex exec --sandbox workspace-write --add-dir /path/to/blog-workspace -
```

To verify the recorded batch, point Hugo at a checkout of the published blog tree and build into a fresh directory.

```sh
output=$(mktemp -d)
hugo --source /path/to/blog --gc --minify --destination "$output"
python3 harness.py verify examples/first-batch.json "$output"
python3 harness.py verify examples/first-batch.json "$output" --live https://archit15singh.github.io
python3 -m unittest discover -s tests
```

The verifier checks article count within the manifest, rendered titles and body, cited links, figure alt text, and artifact links. Live checks also compare article text and asset bytes against the supplied build. The claim ledger is an editorial review input. A passing check proves that the expected content shipped and still leaves source interpretation to the editor.

See the [first publication run](examples/first-run.md) for outcomes and the verifier change it prompted.

## LinkedIn tracking

Record approval for exact post copy and times, then schedule in LinkedIn or with an authorized scheduler. Use the private SQLite tracker for schedule confirmation, publication receipts, comment drafts for manual review, and post analytics.

See [the LinkedIn workflow](LINKEDIN.md) for setup, daily checks, and weekly review.

## Contributing

Use the [architecture improvement loop](ARCHITECTURE.md) for changes to code or CI and when an editorial run exposes a recurring workaround. The original [project build prompt](prompts/build-harness.md) is available for reuse.
