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
MAX_POSTS = 1
GITHUB_USER = "dukduk12"
MAX_LANGUAGES = 6


@dataclass(frozen=True)
class Post:
    title: str
    url: str
    date: str = ""
    image: str = ""


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


class PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.image:
            return
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("property") in {"og:image", "twitter:image"}:
            self.image = attributes.get("content") or ""
        elif tag == "img":
            self.image = attributes.get("src") or ""


def preview_image(url: str) -> str:
    parser = PreviewParser()
    parser.feed(fetch(url).decode("utf-8"))
    return urljoin(url, parser.image) if parser.image else ""


def blog_posts() -> list[Post]:
    parser = BlogParser()
    parser.feed(fetch(BLOG_URL).decode("utf-8"))
    if not parser.posts:
        raise RuntimeError("No blog posts found")
    posts = []
    for post in parser.posts[:MAX_POSTS]:
        image = preview_image(post.url)
        posts.append(Post(post.title, post.url, post.date, image))
    return posts


def medium_posts() -> list[Post]:
    root = ET.fromstring(fetch(MEDIUM_FEED))
    posts: list[Post] = []
    for item in root.findall("./channel/item")[:MAX_POSTS]:
        title = html.unescape((item.findtext("title") or "").strip())
        url = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        date = parsedate_to_datetime(published).strftime("%Y.%m.%d") if published else ""
        encoded = item.findtext(
            "{http://purl.org/rss/1.0/modules/content/}encoded"
        ) or ""
        image_match = re.search(r'<img[^>]+src=["\']([^"\']+)', encoded)
        image = html.unescape(image_match.group(1)) if image_match else ""
        if title and url:
            posts.append(Post(title, url, date, image))
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
    for index, post in enumerate(posts):
        clean_title = post.title.replace("[검토중|", "[")
        title = html.escape(clean_title)
        url = html.escape(post.url, quote=True)
        date = f"<br><sub>{html.escape(post.date)}</sub>" if post.date else ""
        if index == 0 and post.image:
            image = html.escape(post.image, quote=True)
            lines.append(
                f'<a href="{url}"><img src="{image}" alt="{title}" '
                'width="720"></a>'
            )
        lines.append(f'<p><a href="{url}"><strong>{title}</strong></a>{date}</p>')
    return "\n".join(lines)


def generate_language_svg(languages: list[tuple[str, float]]) -> str:
    width = 600
    padding = 25
    bar_y = 55
    bar_height = 10
    legend_y_start = 95
    col_width = 270
    row_height = 25
    
    num_langs = len(languages)
    num_rows = (num_langs + 2 - 1) // 2
    height = legend_y_start + num_rows * row_height + padding - 5
    
    color_map = {
        "Jupyter Notebook": "#DA5B0B",
        "Python": "#3572A5",
        "JavaScript": "#f1e05a",
        "TypeScript": "#3178c6",
        "SCSS": "#c6538c",
        "CSS": "#563d7c",
        "HTML": "#e34c26",
        "Java": "#b07219",
        "Shell": "#89e051",
    }
    default_color = "#858585"
    
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">')
    svg.append(f'  <rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="4.5" fill="#2e3440" stroke="#3b4252"/>')
    svg.append('  <text x="25" y="35" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif" font-size="16" font-weight="600" fill="#88c0d0">Most Used Languages</text>')
    
    bar_width = width - (padding * 2)
    current_x = padding
    
    bar_segments = []
    legend_items = []
    
    total_percentage = sum(p for _, p in languages)
    
    for index, (lang, pct) in enumerate(languages):
        color = color_map.get(lang, default_color)
        seg_w = (pct / 100.0) * bar_width if total_percentage > 0 else 0
        if seg_w > 0:
            bar_segments.append((current_x, seg_w, color))
            current_x += seg_w
        
        col = index % 2
        row = index // 2
        lx = padding + col * col_width
        ly = legend_y_start + row * row_height
        legend_items.append((lx, ly, lang, pct, color))
        
    svg.append('  <defs>')
    svg.append('    <clipPath id="bar-clip">')
    svg.append(f'      <rect x="{padding}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="5" />')
    svg.append('    </clipPath>')
    svg.append('  </defs>')
    
    svg.append('  <g clip-path="url(#bar-clip)">')
    for x, w, color in bar_segments:
        svg.append(f'    <rect x="{x}" y="{bar_y}" width="{w}" height="{bar_height}" fill="{color}" />')
    svg.append('  </g>')
    
    for lx, ly, lang, pct, color in legend_items:
        svg.append(f'  <circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{color}" />')
        svg.append(f'  <text x="{lx+18}" y="{ly}" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif" font-size="12" font-weight="500" fill="#d8dee9">{lang}</text>')
        svg.append(f'  <text x="{lx+180}" y="{ly}" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif" font-size="12" fill="#81a1c1">{pct:.1f}%</text>')
        
    svg.append('</svg>')
    return "\n".join(svg)


def render_languages(languages: list[tuple[str, float]]) -> str:
    svg_content = generate_language_svg(languages)
    svg_path = Path("assets/languages.svg")
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg_content, encoding="utf-8")
    
    return f'<p align="center">\n  <img src="./assets/languages.svg" alt="Languages Overview" width="600">\n</p>'


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
