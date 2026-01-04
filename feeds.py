"""RSS Feed Parser for Newsletter Generator."""

import re
import httpx
import feedparser
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass
class FeedPost:
  title: str
  link: str
  published: Optional[datetime]
  content: str
  source: str


def parse_date(entry) -> Optional[datetime]:
  for attr in ['published_parsed', 'updated_parsed', 'created_parsed']:
    parsed = getattr(entry, attr, None)
    if parsed:
      try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
      except:
        pass
  return None


def clean_html(html: str) -> str:
  if not html:
    return ""
  text = re.sub(r'<[^>]+>', '', html)
  text = re.sub(r'\s+', ' ', text)
  return text.strip()


def get_full_content(entry) -> str:
  if 'content' in entry and entry.content:
    for c in entry.content:
      if isinstance(c, dict) and c.get('value'):
        return clean_html(c['value'])
  summary = entry.get('summary', entry.get('description', ''))
  return clean_html(summary)


def fetch_feed(url: str, timeout: float = 15.0) -> tuple[str, list[FeedPost]]:
  try:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    source_name = feed.feed.get('title', url.split('/')[2])
    posts = []
    for entry in feed.entries:
      post = FeedPost(
        title=entry.get('title', 'Untitled'),
        link=entry.get('link', ''),
        published=parse_date(entry),
        content=get_full_content(entry),
        source=source_name,
      )
      posts.append(post)
    return source_name, posts
  except Exception as e:
    print(f"[RSS] Error fetching {url}: {e}")
    return url, []


def fetch_recent_posts(feed_urls: list[str], hours: int = 48, max_per_feed: int = 10) -> dict[str, list[FeedPost]]:
  cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
  results = {}
  for url in feed_urls:
    print(f"[RSS] Fetching {url}...")
    source_name, posts = fetch_feed(url)
    recent = [p for p in posts if p.published is None or p.published >= cutoff][:max_per_feed]
    results[source_name] = recent
    print(f"[RSS] Found {len(recent)} recent posts from {source_name}")
  return results


def format_posts_for_prompt(feeds_data: dict[str, list[FeedPost]], hours: int = 48) -> str:
  if not feeds_data:
    return "<rss_feeds>\nNo feeds were fetched.\n</rss_feeds>"
  lines = ["<rss_feeds>"]
  for source_name, posts in feeds_data.items():
    lines.append(f"\n<feed source=\"{source_name}\">")
    if not posts:
      lines.append(f"\n<no_recent_posts>No posts from the last {hours} hours.</no_recent_posts>")
    else:
      for post in posts:
        date_str = post.published.strftime("%Y-%m-%d %H:%M UTC") if post.published else "Unknown"
        lines.append(f"\n<article>")
        lines.append(f"<title>{post.title}</title>")
        lines.append(f"<link>{post.link}</link>")
        lines.append(f"<date>{date_str}</date>")
        lines.append(f"<content>\n{post.content}\n</content>")
        lines.append(f"</article>")
    lines.append(f"\n</feed>")
  lines.append("\n</rss_feeds>")
  return "\n".join(lines)

