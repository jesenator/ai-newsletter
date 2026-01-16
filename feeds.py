"""Source fetcher for Newsletter Generator - handles RSS and scraping."""

import json
import os
import re
import httpx
import feedparser
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass
class SourcePost:
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


def is_rss_url(url: str) -> bool:
  """Check if URL looks like an RSS feed based on path patterns."""
  patterns = ['/feed', '/rss', '.xml', '/atom', 'feed.xml', 'rss.xml', 'index.xml']
  url_lower = url.lower()
  return any(p in url_lower for p in patterns)


def try_parse_rss(url: str, timeout: float = 15.0) -> tuple[bool, str, list[SourcePost]]:
  """Try to fetch and parse as RSS. Returns (is_rss, source_name, posts)."""
  try:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get('content-type', '').lower()
    is_xml = 'xml' in content_type or 'rss' in content_type or 'atom' in content_type
    feed = feedparser.parse(response.text)
    if feed.entries and (is_xml or feed.bozo == 0 or len(feed.entries) > 0):
      source_name = feed.feed.get('title', url.split('/')[2])
      posts = []
      for entry in feed.entries:
        post = SourcePost(
          title=entry.get('title', 'Untitled'),
          link=entry.get('link', ''),
          published=parse_date(entry),
          content=get_full_content(entry),
          source=source_name,
        )
        posts.append(post)
      return True, source_name, posts
    return False, url, []
  except Exception as e:
    print(f"[RSS] Error trying RSS for {url}: {e}")
    return False, url, []


def scrape_url_markdown(url: str, max_chars: int = 20000) -> str:
  """Scrape a webpage via Serper."""
  if not os.getenv("SERPER_API_KEY"):
    return "Skipped (SERPER_API_KEY not set)."
  try:
    import http.client
    conn = http.client.HTTPSConnection("scrape.serper.dev")
    payload = json.dumps({"url": url, "includeMarkdown": True})
    headers = {
      'X-API-KEY': os.getenv("SERPER_API_KEY"),
      'Content-Type': 'application/json'
    }
    conn.request("POST", "/", payload, headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))
    md = data.get("markdown") or data.get("text") or data.get("message")
    text = str(md) if md else json.dumps(data)
    if len(text) > max_chars:
      text = text[:max_chars] + "\n...[truncated]..."
    return text
  except Exception as e:
    return f"Error scraping {url}: {e}"


def fetch_source(url: str, hours: int, max_per_feed: int, max_scrape_chars: int) -> tuple[str, list[SourcePost], bool]:
  """Fetch a single source. Returns (source_name, posts, was_rss)."""
  cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
  if is_rss_url(url):
    is_rss, source_name, posts = try_parse_rss(url)
    if is_rss:
      recent = [p for p in posts if p.published is None or p.published >= cutoff][:max_per_feed]
      print(f"[RSS] {source_name}: {len(recent)} recent posts")
      return source_name, recent, True

  is_rss, source_name, posts = try_parse_rss(url)
  if is_rss and posts:
    recent = [p for p in posts if p.published is None or p.published >= cutoff][:max_per_feed]
    print(f"[RSS] {source_name}: {len(recent)} recent posts")
    return source_name, recent, True

  print(f"[SCRAPE] {url}")
  content = scrape_url_markdown(url, max_scrape_chars)
  domain = url.split('/')[2].replace('www.', '')
  post = SourcePost(
    title=domain,
    link=url,
    published=datetime.now(timezone.utc),
    content=content,
    source=domain,
  )
  return domain, [post], False


def fetch_all_sources(urls: list[str], hours: int = 48, max_per_feed: int = 10, max_scrape_chars: int = 20000) -> dict[str, tuple[list[SourcePost], bool]]:
  """Fetch all sources. Returns {source_name: (posts, was_rss)}."""
  results = {}
  for url in urls:
    source_name, posts, was_rss = fetch_source(url, hours, max_per_feed, max_scrape_chars)
    results[source_name] = (posts, was_rss)
  return results


def format_sources_for_prompt(sources_data: dict[str, tuple[list[SourcePost], bool]], hours: int = 48) -> str:
  if not sources_data:
    return "<sources>\nNo sources were fetched.\n</sources>"

  rss_sources = {k: v[0] for k, v in sources_data.items() if v[1]}
  scraped_sources = {k: v[0] for k, v in sources_data.items() if not v[1]}

  lines = ["<sources>"]

  if rss_sources:
    lines.append("\n<rss_feeds>")
    for source_name, posts in rss_sources.items():
      lines.append(f"\n<feed source=\"{source_name}\">")
      if not posts:
        lines.append(f"<no_recent_posts>No posts from the last {hours} hours.</no_recent_posts>")
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

  if scraped_sources:
    lines.append("\n<scraped_sources>")
    for source_name, posts in scraped_sources.items():
      for post in posts:
        lines.append(f"\n<source url=\"{post.link}\">")
        lines.append(f"<content>\n{post.content}\n</content>")
        lines.append("</source>")
    lines.append("\n</scraped_sources>")

  lines.append("\n</sources>")
  return "\n".join(lines)
