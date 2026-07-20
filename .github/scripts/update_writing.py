from __future__ import annotations

import html
import json
import os
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
MAX_POSTS = 2
GITHUB_USER = "dukduk12"
MAX_LANGUAGES = 6


@dataclass(frozen=True)
class Post:
    title: str
    url: str
    date: str = ""


def fetch(url: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
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


def language_stats() -> list[tuple[str, float]]:
    repositories = json.loads(
        fetch(
            f"https://api.github.com/users/{GITHUB_USER}/repos"
            "?type=owner&per_page=100&sort=updated"
        )
    )
    totals: dict[str, int] = {}
    for repository in repositories:
        if repository.get("fork") or repository.get("private"):
            continue
        languages = json.loads(fetch(repository["languages_url"]))
        for language, byte_count in languages.items():
            totals[language] = totals.get(language, 0) + int(byte_count)

    total_bytes = sum(totals.values())
    if not total_bytes:
        raise RuntimeError("No public repository language data found")

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [
        (language, byte_count / total_bytes * 100)
        for language, byte_count in ranked[:MAX_LANGUAGES]
    ]


def render_posts(posts: list[Post]) -> str:
    lines = []
    for post in posts:
        clean_title = post.title.replace("[검토중|", "[")
        title = html.escape(clean_title)
        url = html.escape(post.url, quote=True)
        date = f"<br><sub>{html.escape(post.date)}</sub>" if post.date else ""
        lines.append(f'<p><a href="{url}"><strong>{title}</strong></a>{date}</p>')
    return "\n".join(lines)


def render_languages(languages: list[tuple[str, float]]) -> str:
    rows = [
        "<table>",
        "  <tr><th align=\"left\">Language</th><th align=\"left\">Share</th><th align=\"right\">%</th></tr>",
    ]
    for language, percentage in languages:
        filled = max(1, round(percentage / 5))
        bar = "■" * filled + "□" * (20 - filled)
        rows.append(
            "  <tr>"
            f"<td><strong>{html.escape(language)}</strong></td>"
            f"<td><code>{bar}</code></td>"
            f"<td align=\"right\"><strong>{percentage:.1f}%</strong></td>"
            "</tr>"
        )
    rows.append("</table>")
    return "\n".join(rows)


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
        ("LANGUAGE-STATS", language_stats),
    ):
        try:
            content = (
                render_languages(loader())
                if tag == "LANGUAGE-STATS"
                else render_posts(loader())
            )
            document = replace_block(document, tag, content)
        except Exception as error:
            errors.append(f"{tag}: {error}")

    if len(errors) == 3:
        print("\n".join(errors), file=sys.stderr)
        return 1

    README.write_text(document, encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
