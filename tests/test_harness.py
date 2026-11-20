import io
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from harness import check_batch, goal

SITE = "https://blog.example"
POST = "/posts/example/"
COVER = "/images/cover.webp"
FIGURE = "/downloads/chart.webp"
MODEL = "/downloads/model.py"
SOURCES = ["https://source.example/one", "https://source.example/two"]
MANIFEST = {
    "site": SITE, "count": 1, "posts": [
        {"path": POST, "title": "Example", "cover": COVER, "sources": SOURCES,
         "claims": [{"type": "reported", "claim": "Observed value", "basis": SOURCES[0],
                     "limit": "Source report"}],
         "figures": [{"path": FIGURE, "class": "series-figure"}], "artifacts": [MODEL]}
    ]
}
HTML = f"""<h1 class=post-title>Example</h1>
<img src={SITE}{COVER} alt="Cover">
<div class=post-content>
<p>New body.</p><figure class=series-figure><img src={FIGURE} alt="Chart"></figure>
<a href={SOURCES[0]}>One</a><a href={SOURCES[1]}>Two</a><a href={MODEL}>Script</a>
</div>""".encode()


class Response(io.BytesIO):
    def __init__(self, url, data):
        super().__init__(data)
        self.url = url


class HarnessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = Path(folder.name)
        self.rendered = {POST: HTML, COVER: b"cover", FIGURE: b"chart", MODEL: b"model"}
        for path, data in self.rendered.items():
            file = self.output / path.lstrip("/")
            if path == POST:
                file = file / "index.html"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)

    def live_response(self, request, timeout):
        return Response(request.full_url, self.rendered[urlsplit(request.full_url).path])

    def test_default_goal_is_local_and_scoped(self):
        prompt = goal({"author": "Example"}, 3, False)
        self.assertIn("exactly 3", prompt)
        self.assertIn("Leave the result local", prompt)
        self.assertIn("explicitly authorized", goal({}, 1, True))

    def test_hugo_absolute_cover_and_relative_figure(self):
        check_batch(MANIFEST, self.output)
        with patch("harness.urlopen", self.live_response):
            check_batch(MANIFEST, self.output, SITE)

    def test_incomplete_local_batch_does_not_request_live_pages(self):
        batch = deepcopy(MANIFEST)
        missing = {**batch["posts"][0], "path": "/posts/missing/"}
        batch["posts"].append(missing)
        batch["count"] = 2
        with patch("harness.urlopen", side_effect=self.live_response) as fetch:
            with self.assertRaises(FileNotFoundError):
                check_batch(batch, self.output, SITE)
        fetch.assert_not_called()

    def test_rejects_external_cover_with_identical_path(self):
        page = self.output / POST.lstrip("/") / "index.html"
        page.write_bytes(HTML.replace(SITE.encode(), b"https://elsewhere.example"))
        with self.assertRaisesRegex(ValueError, "cover absent"):
            check_batch(MANIFEST, self.output)

    def test_rejects_stale_body_even_with_matching_title(self):
        self.rendered[POST] = HTML.replace(b"New body.", b"Stale body.")
        with patch("harness.urlopen", self.live_response):
            with self.assertRaisesRegex(ValueError, "live copy differs"):
                check_batch(MANIFEST, self.output, SITE)

    def test_rejects_stale_figure_markup_even_with_matching_text(self):
        self.rendered[POST] = HTML.replace(b" class=series-figure", b"")
        with patch("harness.urlopen", self.live_response):
            with self.assertRaisesRegex(ValueError, "missing figure class"):
                check_batch(MANIFEST, self.output, SITE)

    def test_rejects_stale_asset_even_with_matching_body(self):
        self.rendered[FIGURE] = b"stale"
        with patch("harness.urlopen", self.live_response):
            with self.assertRaisesRegex(ValueError, "live asset differs"):
                check_batch(MANIFEST, self.output, SITE)


if __name__ == "__main__":
    unittest.main()
