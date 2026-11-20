# First run · 20 November 2026

The batch applies the same reliability question at three different boundaries. What has to remain true before you trust a result, expand a rollout, or send production traffic back to an old system?

| Post | Artifact | Key distinction |
| --- | --- | --- |
| [An agent benchmark needs a resource budget](https://archit15singh.github.io/posts/2026-11-20-agent-benchmarks-need-resource-budgets/) | Reported infrastructure error rates under three resource settings | Benchmark success depends in part on the execution environment. |
| [A canary needs enough traffic to fail](https://archit15singh.github.io/posts/2026-11-20-canaries-need-a-sample-budget/) | Independent-request detection curve | The exposure limit and the minimum relevant sample are different release decisions. |
| [An online migration can quietly lose its rollback](https://archit15singh.github.io/posts/2026-11-20-online-migration-rollback-expires/) | One-record history across a read and write cutover | Read parity can expire after a write reaches only the new store. |

The [batch manifest](first-batch.json) records sources, claim types, and limits. The [plot script](https://archit15singh.github.io/downloads/software-reliability/experiment.py) reproduces the plots and sample thresholds.

## What changed during the run

- The initial verifier matched relative figure URLs and failed on absolute cover URLs from Hugo. It now accepts same-origin absolute image URLs, distinguishes inline figures from covers, and rejects an off-site image with the same path.
- Browser inspection found CSS stretching the original charts. The blog now uses its existing responsive figure class. The manifest carries that class and the verifier checks it on both rendered and live pages, so an older page with the same article text and image bytes fails.
- [Blog publication PR](https://github.com/archit15singh/archit15singh.github.io/pull/38) and [responsive figure PR](https://github.com/archit15singh/archit15singh.github.io/pull/39).

## Release checks

- The [Hugo build](https://github.com/archit15singh/archit15singh.github.io/actions/runs/44762020073) and [Pages deployment](https://github.com/archit15singh/archit15singh.github.io/actions/runs/44762070275) passed for blog commit `88148dfb88fda2c7f9848c544317a0be5b3d5d1b`.
- Verified all three article bodies, cited links, chart markup and download links against a rebuild of that commit. All seven unique assets matched by SHA-256. The three routes appeared on the home page, archive, post list and sitemap.
- The three inline charts rendered at 720 × 405 px on desktop and 347 × 195 px at a 390 px viewport. Rerunning the plot script reproduced all six images byte for byte in the same environment.
