from __future__ import annotations

import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


README = Path("README.md")
BLOG_URL = "https://dukduk12.github.io/posts/"
MEDIUM_FEED = "https://medium.com/feed/@sallyinner59"
USER_AGENT = "dukduk12-profile-readme/1.0"
MAX_POSTS = 3


@dataclass(frozen=True)
class Post:
    title: str
    url: str
    date: str = ""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


class BlogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_heading = False
        self.current_url = ""
        self.current_text: list[str] = []
        self.posts: list[Post] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h2":
            self.in_heading = True
        elif self.in_heading and tag == "a":
            self.current_url = dict(attrs).get("href") or ""
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.in_heading and self.current_url:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.in_heading and self.current_url:
            title = " ".join("".join(self.current_text).split())
            if title:
                self.posts.append(
                    Post(html.unescape(title), urljoin(BLOG_URL, self.current_url))
                )
            self.current_url = ""
            self.current_text = []
        elif tag == "h2":
            self.in_heading = False


def blog_posts() -> list[Post]:
    parser = BlogParser()
    parser.feed(fetch(BLOG_URL).decode("utf-8"))
    if not parser.posts:
        raise RuntimeError("No blog posts found")
    return parser.posts[:MAX_POSTS]


def medium_posts() -> list[Post]:
    root = ET.fromstring(fetch(MEDIUM_FEED))
    posts: list[Post] = []
    for item in root.findall("./channel/item")[:MAX_POSTS]:
        title = html.unescape((item.findtext("title") or "").strip())
        url = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        date = parsedate_to_datetime(published).strftime("%Y.%m.%d") if published else ""
        if title and url:
            posts.append(Post(title, url, date))
    if not posts:
        raise RuntimeError("No Medium posts found")
    return posts


def markdown(posts: list[Post]) -> str:
    lines = []
    for post in posts:
        title = re.sub(r"([\\[\]])", r"\\\1", post.title)
        suffix = f" · <sub>{post.date}</sub>" if post.date else ""
        lines.append(f"- [{title}]({post.url}){suffix}")
    return "\n".join(lines)


def replace_block(document: str, tag: str, content: str) -> str:
    start = f"<!-- {tag}:START -->"
    end = f"<!-- {tag}:END -->"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
    replacement = f"{start}\n{content}\n{end}"
    updated, count = pattern.subn(replacement, document)
    if count != 1:
        raise RuntimeError(f"Expected one {tag} block, found {count}")
    return updated


def main() -> int:
    document = README.read_text(encoding="utf-8")
    errors: list[str] = []

    for tag, loader in (
        ("BLOG-POST-LIST", blog_posts),
        ("MEDIUM-POST-LIST", medium_posts),
    ):
        try:
            document = replace_block(document, tag, markdown(loader()))
        except Exception as error:
            errors.append(f"{tag}: {error}")

    if len(errors) == 2:
        print("\n".join(errors), file=sys.stderr)
        return 1

    README.write_text(document, encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
