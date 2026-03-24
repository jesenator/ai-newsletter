"""Source fetcher - unified entry point for RSS, web scraping, and Twitter."""

import json
import os
import re
import httpx
import feedparser
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

from logger import log_info, log_error, log_debug


@dataclass
class SourcePost:
  title: str
  link: str
  published: Optional[datetime]
  content: str
  source: str


def parse_twitter_url(url: str) -> tuple[str, str] | None:
  """Returns ('profile', username) or ('list', list_id) or None."""
  list_match = re.match(r'https?://(?:twitter\.com|x\.com)/i/lists/(\d+)', url)
  if list_match:
    return ('list', list_match.group(1))
  profile_match = re.match(r'https?://(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/?$', url)
  if profile_match:
    username = profile_match.group(1)
    reserved = {'i', 'home', 'explore', 'search', 'settings', 'notifications', 'messages', 'compose'}
    if username.lower() not in reserved:
      return ('profile', username)
  return None


def _is_rss_url(url: str) -> bool:
  patterns = ['/feed', '/rss', '.xml', '/atom', 'feed.xml', 'rss.xml', 'index.xml']
  url_lower = url.lower()
  return any(p in url_lower for p in patterns)


def classify_urls(urls: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
  """Split URLs into (rss_urls, scrape_urls, twitter_profiles, twitter_lists)."""
  rss_urls, scrape_urls, twitter_profiles, twitter_lists = [], [], [], []
  for url in urls:
    tw = parse_twitter_url(url)
    if tw and tw[0] == 'profile':
      twitter_profiles.append(tw[1])
    elif tw and tw[0] == 'list':
      twitter_lists.append(tw[1])
    elif _is_rss_url(url):
      rss_urls.append(url)
    else:
      scrape_urls.append(url)
  return rss_urls, scrape_urls, twitter_profiles, twitter_lists


# --- RSS / Scrape internals ---

def _parse_date(entry) -> Optional[datetime]:
  for attr in ['published_parsed', 'updated_parsed', 'created_parsed']:
    parsed = getattr(entry, attr, None)
    if parsed:
      try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
      except:
        pass
  return None


def _clean_html(html: str) -> str:
  if not html:
    return ""
  text = re.sub(r'<[^>]+>', '', html)
  text = re.sub(r'\s+', ' ', text)
  return text.strip()


def _get_full_content(entry) -> str:
  if 'content' in entry and entry.content:
    for c in entry.content:
      if isinstance(c, dict) and c.get('value'):
        return _clean_html(c['value'])
  summary = entry.get('summary', entry.get('description', ''))
  return _clean_html(summary)


RSS_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

def _try_parse_rss(url: str, timeout: float = 15.0) -> tuple[bool, str, list[SourcePost]]:
  try:
    response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=RSS_HEADERS)
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
          published=_parse_date(entry),
          content=_get_full_content(entry),
          source=source_name,
        )
        posts.append(post)
      log_debug(f"[RSS] Parsed {source_name}: {len(posts)} entries")
      return True, source_name, posts
    return False, url, []
  except Exception as e:
    print(f"[RSS] Error trying RSS for {url}: {e}")
    log_error(f"RSS parse failed for {url}", e)
    return False, url, []


def _scrape_url_markdown(url: str, max_chars: int = 20000) -> str:
  if not os.getenv("SERPER_API_KEY"):
    log_error("SERPER_API_KEY not set, skipping scrape")
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
    log_debug(f"[SCRAPE] {url}: {len(text)} chars")
    return text
  except Exception as e:
    log_error(f"Scrape failed for {url}", e)
    return f"Error scraping {url}: {e}"


def _fetch_rss_feed(url: str, hours: int, max_per_feed: int) -> tuple[str, list[SourcePost]] | None:
  """Fetch an RSS feed. Returns (source_name, posts) or None if parse fails."""
  is_rss, source_name, posts = _try_parse_rss(url)
  if not is_rss:
    return None
  cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
  recent = [p for p in posts if p.published is None or p.published >= cutoff][:max_per_feed]
  print(f"[RSS] {source_name}: {len(recent)} recent posts")
  log_info(f"[SOURCE] RSS {source_name}: {len(recent)} recent posts from {url}")
  return source_name, recent


def _fetch_scraped_page(url: str, max_chars: int) -> tuple[str, list[SourcePost]]:
  """Scrape a web page. Returns (source_name, posts)."""
  print(f"[SCRAPE] {url}")
  log_info(f"[SOURCE] Scraping {url}")
  content = _scrape_url_markdown(url, max_chars)
  domain = url.split('/')[2].replace('www.', '')
  post = SourcePost(
    title=domain, link=url,
    published=datetime.now(timezone.utc),
    content=content, source=domain,
  )
  return domain, [post]


# --- Unified fetch ---

def fetch_all(urls: list[str], hours: int = 48, max_per_feed: int = 10, max_scrape_chars: int = 20000) -> tuple[dict, dict, list[dict]]:
  """Fetch all sources. Returns (rss_feeds, scraped_pages, filtered_tweets) where
    rss_feeds = {source_name: list[SourcePost]}
    scraped_pages = {source_name: list[SourcePost]}
    filtered_tweets = list of filtered tweet dicts
  """
  rss_urls, scrape_urls, twitter_profiles, twitter_lists = classify_urls(urls)

  print(f"\nFetching sources (last {hours} hours)...")
  print(f"  RSS: {len(rss_urls)}, Scrape: {len(scrape_urls)}, Twitter profiles: {len(twitter_profiles)}, Twitter lists: {len(twitter_lists)}")

  rss_feeds = {}
  scraped_pages = {}

  for url in rss_urls:
    result = _fetch_rss_feed(url, hours, max_per_feed)
    if result:
      rss_feeds[result[0]] = result[1]
    else:
      log_info(f"RSS parse failed for {url}, falling back to scrape")
      name, posts = _fetch_scraped_page(url, max_scrape_chars)
      scraped_pages[name] = posts

  for url in scrape_urls:
    name, posts = _fetch_scraped_page(url, max_scrape_chars)
    scraped_pages[name] = posts

  tweets = []
  if twitter_profiles or twitter_lists:
    try:
      from twitter import TwitterClient
      client = TwitterClient()
      raw_tweets = client.fetch_all(twitter_profiles, twitter_lists, hours=hours)
      tweets = client.filter_tweets(raw_tweets)
      print(f"[Twitter] {len(raw_tweets)} raw -> {len(tweets)} filtered tweets")
    except Exception as e:
      print(f"[Twitter] Error fetching tweets: {e}")
      log_error("[Twitter] Error fetching tweets", e)

  return rss_feeds, scraped_pages, tweets


# --- Formatting ---

def format_rss_for_prompt(rss_feeds: dict[str, list[SourcePost]], hours: int = 48) -> str:
  if not rss_feeds:
    return "No RSS feeds were fetched."
  lines = []
  for source_name, posts in rss_feeds.items():
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
  return "\n".join(lines)


def format_scraped_for_prompt(scraped_pages: dict[str, list[SourcePost]]) -> str:
  if not scraped_pages:
    return "No pages were scraped."
  lines = []
  for source_name, posts in scraped_pages.items():
    for post in posts:
      lines.append(f"\n<source url=\"{post.link}\">")
      lines.append(f"<content>\n{post.content}\n</content>")
      lines.append("</source>")
  return "\n".join(lines)


def format_tweets_for_prompt(tweets: list[dict]) -> str:
  from twitter import format_tweets_xml
  return format_tweets_xml(tweets)
