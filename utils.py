"""Utility functions for newsletter generation."""

import json
import os
import re
from pathlib import Path


def ensure_data_dir(data_dir: Path):
  data_dir.mkdir(exist_ok=True)


def load_history(data_dir: Path) -> dict:
  history_file = data_dir / "history.json"
  if history_file.exists():
    return json.loads(history_file.read_text())
  return {"newsletters": []}


def save_history(data_dir: Path, history: dict):
  ensure_data_dir(data_dir)
  history_file = data_dir / "history.json"
  history_file.write_text(json.dumps(history, indent=2))


def save_newsletter(data_dir: Path, content: str, date: str) -> Path:
  ensure_data_dir(data_dir)
  filename = f"newsletter_{date.replace(' ', '_').replace(',', '')}.html"
  newsletter_file = data_dir / filename
  newsletter_file.write_text(content)
  return newsletter_file


def open_in_browser(filepath: Path):
  import subprocess
  subprocess.run(["open", str(filepath)])


def clean_html_output(content: str) -> str:
  content = re.sub(r"```html\s*", "", content)
  content = re.sub(r"```\s*", "", content)
  html_match = re.search(
    r"(<!DOCTYPE html>.*?</html>|<html>.*?</html>)",
    content,
    re.DOTALL | re.IGNORECASE,
  )
  if html_match:
    return html_match.group(1)
  return content.strip()


def strip_tags(text: str) -> str:
  if not text:
    return ""
  text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"[^\S\n]+", " ", text)  # collapse spaces/tabs but keep newlines
  text = re.sub(r" *\n", "\n", text)  # remove trailing spaces before newlines
  text = re.sub(r"\n{3,}", "\n\n", text)  # max 2 newlines
  return text.strip()


def truncate(text: str, max_chars: int) -> str:
  if not text:
    return ""
  if len(text) <= max_chars:
    return text
  return text[:max_chars] + "\n...[truncated]..."


def scrape_url_markdown(url: str) -> str:
  """Scrape a webpage via Serper."""
  import http.client
  try:
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
    if md:
      return str(md)
    return json.dumps(data)
  except Exception as e:
    return f"Error scraping {url}: {e}"


def fetch_other_sources_for_prompt(other_sources: list[str], max_chars: int) -> str:
  if not os.getenv("SERPER_API_KEY"):
    print("[OTHER] SERPER_API_KEY is not set. Skipping pre-scrape.")
    lines = ["<other_sources>"]
    for url in other_sources:
      lines.append(f"\n<source url=\"{url}\">")
      lines.append("<content>Skipped (SERPER_API_KEY not set).</content>")
      lines.append("</source>")
    lines.append("\n</other_sources>")
    return "\n".join(lines)

  lines = ["<other_sources>"]
  for url in other_sources:
    print(f"[OTHER] Scraping {url}")
    content = scrape_url_markdown(url)
    content = truncate(content, max_chars)
    lines.append(f"\n<source url=\"{url}\">")
    if content.strip():
      lines.append(f"<content>\n{content}\n</content>")
    else:
      lines.append("<content>No content fetched.</content>")
    lines.append("</source>")
  lines.append("\n</other_sources>")
  return "\n".join(lines)


def load_recent_newsletters_for_prompt(data_dir: Path, history: dict, n: int) -> str:
  """Load recent newsletters as plain text (stripped HTML) to avoid repeats."""
  ensure_data_dir(data_dir)
  items = history.get("newsletters", [])[-n:]
  lines = ["<recent_newsletters>"]
  if not items:
    lines.append("<none>No prior newsletters saved.</none>")
    lines.append("</recent_newsletters>")
    return "\n".join(lines)

  for item in items:
    date = item.get("date", "unknown")
    filename = item.get("filename", "")
    path = data_dir / filename if filename else None
    raw = ""
    if path and path.exists():
      raw = path.read_text()
    text = strip_tags(raw)
    lines.append(f"\n<newsletter date=\"{date}\" filename=\"{filename}\">")
    if text.strip():
      lines.append(f"<text>\n{text}\n</text>")
    else:
      lines.append("<text>No content available.</text>")
    lines.append("</newsletter>")
  lines.append("\n</recent_newsletters>")
  return "\n".join(lines)


def load_reference_newsletter(data_dir: Path, filename: str) -> str:
  """Load a specific newsletter as full HTML for format reference."""
  path = data_dir / filename
  if path.exists():
    return path.read_text()
  return ""

