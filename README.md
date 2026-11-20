# Engineering Blog Harness

A bounded workflow for turning first-party engineering reports into original posts. A writing agent researches and edits each piece. The CLI generates a scoped goal and checks Hugo output locally and after deployment.

Use Python 3.10+, Git, and Hugo. For GitHub delivery, use an authenticated GitHub CLI or the destination repository's equivalent release process.

```sh
python3 harness.py goal examples/archit-profile.json --count 3
```

Copy the generated goal into a goal-capable agent session rooted here or provide it to your editor. Add `--publish` for a batch with explicit permission to push and merge on the target blog. The CLI prints the prompt. The agent works through [the editorial run](WORKFLOW.md). The original [harness creation goal](prompts/build-harness.md) is also reusable.

With a signed-in Codex CLI, you can also hand off a local batch from the harness checkout. Use a dedicated writable directory containing the blog checkout and room for its linked worktree. The agent needs primary-source web access for the research step.

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

Harness contributors and editorial agents use the [architecture improvement loop](ARCHITECTURE.md) after changes to code or CI and when an editorial run exposes a recurring workaround.

The [LinkedIn campaign workflow](LINKEDIN.md) adds a private scheduling handoff, comment review queue, post analytics and weekly strategy decisions.
