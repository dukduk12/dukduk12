from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
MAX_LANGUAGES = 10
ASSETS = Path("assets")


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
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to include private repositories")

    repositories = json.loads(
        fetch(
            "https://api.github.com/user/repos"
            "?visibility=all&affiliation=owner&per_page=100&sort=updated"
        )
    )
    totals: dict[str, int] = {}
    for repository in repositories:
        if repository.get("fork"):
            continue
        languages = json.loads(fetch(repository["languages_url"]))
        for language, byte_count in languages.items():
            totals[language] = totals.get(language, 0) + int(byte_count)

    total_bytes = sum(totals.values())
    if not total_bytes:
        raise RuntimeError("No repository language data found")

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


def render_languages(languages: list[tuple[str, float]]) -> str:
    width = 720
    row_height = 28
    height = 54 + row_height * len(languages)
    rows = []
    for index, (language, percentage) in enumerate(languages):
        y = 48 + index * row_height
        bar_width = max(2, round(percentage / 100 * 430))
        rows.append(
            f'<text class="label" x="18" y="{y + 12}">{html.escape(language)}</text>'
            f'<rect class="track" x="180" y="{y}" width="430" height="12" rx="6"/>'
            f'<rect class="bar" x="180" y="{y}" width="{bar_width}" height="12" rx="6"/>'
            f'<text class="value" x="700" y="{y + 11}" text-anchor="end">{percentage:.1f}%</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Most used languages">
<style>
  .bg {{ fill:#fff; stroke:#d0d7de }} .title,.label {{ fill:#24292f }} .value {{ fill:#57606a }}
  .track {{ fill:#eaeef2 }} .bar {{ fill:#24292f }} text {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif }}
  .title {{ font-size:15px;font-weight:600 }} .label,.value {{ font-size:12px }}
  @media (prefers-color-scheme:dark) {{ .bg {{ fill:#0d1117;stroke:#30363d }} .title,.label {{ fill:#f0f6fc }} .value {{ fill:#8b949e }} .track {{ fill:#21262d }} .bar {{ fill:#f0f6fc }} }}
</style>
<rect class="bg" x=".5" y=".5" width="719" height="{height - 1}" rx="8"/>
<text class="title" x="18" y="27">LANGUAGE DISTRIBUTION</text>
{''.join(rows)}
</svg>'''
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "languages.svg").write_text(svg, encoding="utf-8")
    return '<img src="./assets/languages.svg" alt="Monochrome language distribution chart" width="720">'


def github_stats() -> dict:
    """Fetch contribution streak and profile stats via GitHub GraphQL API."""
    query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
          totalCommitContributions
        }
        repositories(ownerAffiliations: OWNER, privacy: PUBLIC) {
          totalCount
        }
        privateRepos: repositories(ownerAffiliations: OWNER, privacy: PRIVATE) {
          totalCount
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": GITHUB_USER}}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read())

    user = data["data"]["user"]
    col = user["contributionsCollection"]
    calendar = col["contributionCalendar"]

    # Days since account creation
    created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    days_on_github = (datetime.now(timezone.utc) - created).days

    # Flatten all days into a date -> count map
    all_days: dict[str, int] = {}
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            all_days[day["date"]] = day["contributionCount"]

    # Calculate current streak
    today = datetime.now(timezone.utc).date()
    check = today if all_days.get(str(today), 0) > 0 else today - timedelta(days=1)
    current_streak = 0
    while all_days.get(str(check), 0) > 0:
        current_streak += 1
        check -= timedelta(days=1)

    # Calculate longest streak
    longest_streak = temp = 0
    for d in sorted(all_days):
        if all_days[d] > 0:
            temp += 1
            longest_streak = max(longest_streak, temp)
        else:
            temp = 0

    return {
        "days_on_github": days_on_github,
        "commits": col["totalCommitContributions"],
        "current": current_streak,
        "longest": longest_streak,
        "repos": user["repositories"]["totalCount"],
        "private_repos": user["privateRepos"]["totalCount"],
        "months": monthly_contributions(all_days),
    }


def monthly_contributions(all_days: dict[str, int]) -> list[tuple[str, int]]:
    months: dict[str, int] = {}
    for date, count in all_days.items():
        key = date[:7]
        months[key] = months.get(key, 0) + count
    return sorted(months.items())[-12:]


def render_overview(stats: dict) -> str:
    commits = stats["commits"]
    cur = stats["current"]
    lng = stats["longest"]
    rep = stats["repos"]
    prv = stats["private_repos"]

    metrics = [
        ("COMMITS THIS YEAR", f"{commits:,}"),
        ("CURRENT STREAK", f"{cur}d"),
        ("LONGEST STREAK", f"{lng}d"),
        ("REPOSITORIES", str(rep + prv)),
    ]
    cards = []
    for index, (label, value) in enumerate(metrics):
        x = 36 + index * 170
        cards.append(f'<text class="metric" x="{x}" y="36">{value}</text><text class="caption" x="{x}" y="54">{label}</text>')

    months = stats["months"]
    peak = max((count for _, count in months), default=1)
    bars = []
    for index, (month, count) in enumerate(months):
        x = 25 + index * 56
        bar_height = max(2, round(count / peak * 92))
        y = 174 - bar_height
        bars.append(
            f'<rect class="monthbar" x="{x}" y="{y}" width="32" height="{bar_height}" rx="4">'
            f'<title>{month}: {count} contributions</title></rect>'
            f'<text class="month" x="{x + 16}" y="193" text-anchor="middle">{month[5:]}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="214" viewBox="0 0 720 214" role="img" aria-label="GitHub overview and monthly contributions">
<style>
  .bg {{ fill:#fff;stroke:#d0d7de }} .metric,.title {{ fill:#24292f }} .caption,.month {{ fill:#57606a }} .axis {{ stroke:#d0d7de }} .monthbar {{ fill:#24292f }}
  text {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif }} .metric {{ font-size:18px;font-weight:650 }} .caption,.month {{ font-size:9px }} .title {{ font-size:12px;font-weight:600 }}
  @media (prefers-color-scheme:dark) {{ .bg {{ fill:#0d1117;stroke:#30363d }} .metric,.title {{ fill:#f0f6fc }} .caption,.month {{ fill:#8b949e }} .axis {{ stroke:#30363d }} .monthbar {{ fill:#f0f6fc }} }}
</style>
<rect class="bg" x=".5" y=".5" width="719" height="213" rx="8"/>
{''.join(cards)}
<text class="title" x="18" y="78">ACTIVITY · LAST 12 MONTHS</text>
<line class="axis" x1="18" y1="174.5" x2="702" y2="174.5"/>
{''.join(bars)}
</svg>'''
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "overview.svg").write_text(svg, encoding="utf-8")
    return '<img src="./assets/overview.svg" alt="Monochrome GitHub overview with monthly contribution graph" width="720">'


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
        ("LANGUAGE-STATS", language_stats),
        ("GITHUB-OVERVIEW", github_stats),
    ):
        try:
            if tag == "LANGUAGE-STATS":
                content = render_languages(loader())
            elif tag == "GITHUB-OVERVIEW":
                content = render_overview(loader())
            else:
                content = render_posts(loader())
            document = replace_block(document, tag, content)
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
