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


def render_languages(languages: list[tuple[str, float]]) -> str:
    rows = ["<pre>"]
    for language, percentage in languages:
        filled = max(1, round(percentage / 5))
        bar = "■" * filled + "□" * (20 - filled)
        rows.append(f"{language[:18]:<18}  {bar}  {percentage:>5.1f}%")
    rows.append("</pre>")
    return "\n".join(rows)


def github_stats() -> dict:
    """Fetch contribution streak and profile stats via GitHub GraphQL API."""
    query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        contributionsCollection {
          totalCommitContributions
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
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
    }


def render_overview(stats: dict) -> str:
    days = stats["days_on_github"]
    commits = stats["commits"]
    cur = stats["current"]
    lng = stats["longest"]
    rep = stats["repos"]
    prv = stats["private_repos"]

    max_streak = max(lng, 1)
    BAR = 20
    dot = "\u00b7"

    def streak_bar(val: int) -> str:
        filled = max(1, round(val / max_streak * BAR)) if val > 0 else 0
        return "\u25a0" * filled + "\u25a1" * (BAR - filled)

    rows = ["<pre>"]
    rows.append(f"{'Days on GitHub':<18}  {dot * BAR}  {days:>6,}")
    rows.append(f"{'Commits This Year':<18}  {dot * BAR}  {commits:>6,}")
    rows.append(f"{'Current Streak':<18}  {streak_bar(cur)}  {cur:>3} days")
    rows.append(f"{'Longest Streak':<18}  {streak_bar(lng)}  {lng:>3} days")
    rows.append(f"{'Public Repos':<18}  {dot * BAR}  {rep:>6}")
    rows.append(f"{'Private Repos':<18}  {dot * BAR}  {prv:>6}")
    rows.append("</pre>")
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

    if len(errors) == 4:
        print("\n".join(errors), file=sys.stderr)
        return 1

    README.write_text(document, encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
