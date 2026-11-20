#!/usr/bin/env python3
"""Compose a bounded editorial goal and verify a built or deployed Hugo batch."""
import argparse
import hashlib
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

VOID = set("area base br col embed hr img input link meta param source track wbr".split())
PATH = re.compile(r"/[a-zA-Z0-9_./-]+")


class Article(HTMLParser):
    """Capture the heading, article body, and rendered resource references."""

    def __init__(self, raw, origin):
        super().__init__(convert_charrefs=True)
        self.origin = urlsplit(origin)[:2]
        self.stack = []
        self.heading = []
        self.body = []
        self.links = set()
        self.images = {}
        self.covers = {}
        self.figure_classes = {}
        self.feed(raw.decode("utf-8"))
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        in_heading, in_body, figure_classes = self.stack[-1][1:] if self.stack else (False, False, ())
        in_heading |= tag == "h1" and "post-title" in classes
        in_body |= "post-content" in classes
        if tag == "figure":
            figure_classes = classes
        if tag not in VOID:
            self.stack.append((tag, in_heading, in_body, figure_classes))
        if in_body and tag == "a":
            self.links.add(attrs.get("href"))
        if tag == "img" and attrs.get("src"):
            src = urlsplit(attrs["src"])
            if src[:2] in (self.origin, ("", "")) and not src.query and not src.fragment:
                images = self.images if in_body else self.covers
                images[src.path] = attrs.get("alt", "")
                if in_body:
                    self.figure_classes[src.path] = figure_classes
        if in_body and tag == "pre":
            self.body.append("::pre::")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack:
            _, in_heading, in_body, _ = self.stack[-1]
            if in_heading:
                self.heading.append(data)
            if in_body:
                self.body.append(data)

    @property
    def text(self):
        return " ".join(" ".join(self.body).split())

    @property
    def title(self):
        return " ".join(" ".join(self.heading).split())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def site_path(value, page=False):
    require(PATH.fullmatch(value) and ".." not in PurePosixPath(value).parts and "//" not in value,
            f"invalid site path: {value}")
    require(value.endswith("/") == page, f"wrong trailing slash: {value}")
    return value


def built_path(output, path):
    return output / path.lstrip("/") / "index.html" if path.endswith("/") else output / path.lstrip("/")


def check_batch(manifest, output, base_url=None):
    posts = manifest["posts"]
    require(len(posts) == manifest["count"] > 0, "manifest post count differs from batch size")
    seen = set()
    cache = {}
    origin = manifest["site"].rstrip("/")
    base = urlsplit(origin)
    require(base.scheme == "https" and base.netloc and not base.path
            and not base.query and not base.fragment and not base.username,
            "manifest site must be an HTTPS origin")
    if base_url:
        require(base_url.rstrip("/") == origin, "live URL must match the manifest site")
    stamp = urlencode({"verify": time.time_ns()})

    def live(path):
        if path not in cache:
            request = Request(base_url.rstrip("/") + path + "?" + stamp,
                              headers={"Cache-Control": "no-cache", "User-Agent": "engineering-blog-harness"})
            with urlopen(request, timeout=20) as response:
                require(urlsplit(response.url)[:3] == (base.scheme, base.netloc, path),
                        f"unexpected redirect for {path}: {response.url}")
                cache[path] = response.read()
        return cache[path]

    for post in posts:
        path = site_path(post["path"], page=True)
        require(path not in seen, f"duplicate post: {path}")
        seen.add(path)
        expected = Article(built_path(output, path).read_bytes(), origin)
        require(expected.title == post["title"], f"{path}: wrong rendered title ({expected.title})")
        require(bool(expected.text), f"{path}: missing article body")
        require(len(set(post["sources"])) >= 2, f"{path}: list at least two primary source URLs")
        assets = set()
        for claim in post["claims"]:
            require(claim["type"] in {"reported", "derived", "scenario"} and all(claim[field].strip() for field in ("basis", "claim", "limit")),
                    f"{path}: claim has no classification or basis")
            if claim["type"] == "reported":
                require(claim["basis"] in post["sources"], f"{path}: reported claim needs a listed source")
        require(bool(post["claims"]), f"{path}: missing claim ledger")

        cover = site_path(post["cover"])

        def check_markup(article):
            require(article.covers.get(cover), f"{path}: cover absent or missing alt text: {cover}")
            assets.add(cover)
            for source in post["sources"]:
                require(urlsplit(source).scheme == "https" and source in article.links,
                        f"{path}: primary source missing from article body: {source}")
            require(bool(post["figures"]), f"{path}: missing figure")
            for figure in post["figures"]:
                route = site_path(figure["path"])
                require(article.images.get(route), f"{path}: figure absent or missing alt text: {route}")
                if css_class := figure.get("class"):
                    require(css_class in article.figure_classes[route],
                            f"{path}: missing figure class {css_class}: {route}")
                assets.add(route)
            for artifact in post["artifacts"]:
                route = site_path(artifact)
                require(route in article.links, f"{path}: artifact link missing: {route}")
                assets.add(route)
            require(bool(post["artifacts"]), f"{path}: missing reproducible artifact")

        check_markup(expected)
        if base_url:
            actual = Article(live(path), origin)
            require((actual.title, actual.text) == (expected.title, expected.text), f"{path}: live copy differs from build")
            check_markup(actual)
            require(actual.covers[cover] == expected.covers[cover], f"{path}: live cover alt differs from build")
            require(all(actual.images[route] == expected.images[route] for route in
                        (figure["path"] for figure in post["figures"])), f"{path}: live alt text differs from build")
        for route in sorted(assets):
            data = built_path(output, route).read_bytes()
            require(bool(data), f"empty asset: {route}")
            if base_url:
                require(hashlib.sha256(data).digest() == hashlib.sha256(live(route)).digest(),
                        f"{route}: live asset differs from build")
        print(f"PASS {path} ({len(assets)} assets)")


def goal(profile, count, publish):
    target = "publish the batch to the configured Hugo site" if publish else "prepare and verify a local batch"
    authorization = ("Treat this as publish mode only if the operator explicitly authorized push and merge "
                     "for this repository and batch." if publish else
                     "Leave the result local. Stop after the build and local verification.")
    return f"""# Editorial goal

Use WORKFLOW.md to {target}. Finish exactly {count} new posts, then report the result and ask what to do next.

{authorization}

Public editorial profile and source leads:

```json
{json.dumps(profile, indent=2)}
```
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("goal", help="print a scoped agent goal")
    seed.add_argument("profile", type=Path)
    seed.add_argument("--count", type=int, required=True)
    seed.add_argument("--publish", action="store_true")
    check = sub.add_parser("verify", help="verify a Hugo build and optionally its live deployment")
    check.add_argument("manifest", type=Path)
    check.add_argument("output", type=Path)
    check.add_argument("--live", metavar="HTTPS_ORIGIN")
    args = parser.parse_args()
    try:
        if args.command == "goal":
            require(args.count > 0, "count must be positive")
            print(goal(read_json(args.profile), args.count, args.publish), end="")
        else:
            check_batch(read_json(args.manifest), args.output, args.live)
    except (ValueError, OSError, URLError, KeyError, TypeError) as error:
        parser.exit(1, f"FAIL {error}\n")


if __name__ == "__main__":
    main()
