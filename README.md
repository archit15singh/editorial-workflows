# Engineering Blog Harness

A bounded workflow for turning first-party engineering reports into original posts. A writing agent researches and edits each piece. The CLI generates a scoped goal and checks Hugo output locally and after deployment.

Use Python 3.10+, Git, and Hugo. For GitHub delivery, use an authenticated GitHub CLI or the destination repository's equivalent release process.

```sh
python3 harness.py goal examples/archit-profile.json --count 3
```

Copy the generated goal into a goal-capable agent session rooted here or provide it to your editor. Add `--publish` for a batch with explicit permission to push and merge on the target blog. The CLI prints the prompt. The agent works through [the editorial run](WORKFLOW.md). The original [harness creation goal](prompts/build-harness.md) is also reusable.

For a Hugo site and the recorded first batch:

```sh
hugo --source /path/to/blog --gc --minify --destination /tmp/blog-verification
python3 harness.py verify examples/first-batch.json /tmp/blog-verification
python3 harness.py verify examples/first-batch.json /tmp/blog-verification --live https://archit15singh.github.io
python3 -m unittest discover -s tests
```

The verifier checks article count within the manifest, rendered titles and body, cited links, figure alt text, and artifact links. Live checks also compare article text and asset bytes against the supplied build. The claim ledger is an editorial review input. A passing check proves that the expected content shipped and still leaves source interpretation to the editor.

See the [first publication run](examples/first-run.md) for outcomes and the verifier change it prompted.
