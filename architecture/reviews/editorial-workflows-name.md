# Public name and verifier identification

Trigger: Rename the repository and change the verifier's HTTP user agent.
Evidence: The previous name described Hugo publishing, while the README linked to LinkedIn tracking only at the end.
Design: Name both workflows on the landing page, and align the user agent with the GitHub slug.
Decision: Keep CLI filenames and arguments so existing automation can keep using its current checkout path.
Verification: All 14 tests pass, and all three recorded articles and nine assets match production after a Hugo build of the published blog tree.
