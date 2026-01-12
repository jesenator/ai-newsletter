#!/usr/bin/env python3
"""
Newsletter Generator - A personalized AI newsletter curator.

Run directly:
  python generate.py
  python generate.py --test
  python generate.py --send-email
  python generate.py --send-email --no-open
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from agents import ModelSettings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, ReplyTo

from agent import Agent
from tools import ALL_TOOLS
from feeds import fetch_recent_posts, format_posts_for_prompt
from utils import (
  clean_html_output,
  fetch_other_sources_for_prompt,
  load_recent_newsletters_for_prompt,
  load_reference_newsletter,
  open_in_browser,
  save_newsletter,
)
from config import (
  NEWSLETTER_NAME, RECIPIENT_EMAIL, FROM_EMAIL, REPLY_TO_EMAIL,
  MODEL, TEST_MODEL, RSS_HOURS,
  RECENT_NEWSLETTERS_TO_INCLUDE, OTHER_SOURCE_MAX_CHARS,
  REFERENCE_NEWSLETTER_FILE,
  RSS_FEEDS, OTHER_SOURCES, PROMPT,
)

DATA_DIR = Path(__file__).parent / "data"

# =============================================================================
# EMAIL SENDING
# =============================================================================

FOOTER_HTML = '''
<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e5e5; font-size: 12px; color: #666; text-align: center;">
  <a href="https://jessewgilbert.com" style="color: #666;">jessewgilbert.com</a> · Reply to this email to unsubscribe or give feedback.
</div>
'''

def append_footer(html_content: str) -> str:
  if '</body>' in html_content:
    return html_content.replace('</body>', FOOTER_HTML + '</body>')
  return html_content + FOOTER_HTML

def send_email(subject: str, html_content: str, to_email: str):
  api_key = os.getenv('SENDGRID_API_KEY')
  if not api_key:
    print("ERROR: SENDGRID_API_KEY not set")
    return False

  message = Mail(
    from_email=FROM_EMAIL,
    to_emails=to_email,
    subject=subject,
    html_content=html_content
  )
  if REPLY_TO_EMAIL:
    message.reply_to = ReplyTo(REPLY_TO_EMAIL)

  try:
    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    print(f"Email sent! Status: {response.status_code}")
    return True
  except Exception as e:
    print(f"ERROR sending email: {e}")
    return False


# =============================================================================
# NEWSLETTER GENERATION
# =============================================================================

def build_prompt():
  now = datetime.now()
  current_date = now.strftime("%B %d, %Y")
  day_of_week = now.strftime("%A")

  print(f"\nFetching RSS feeds (last {RSS_HOURS} hours)...")
  rss_posts = fetch_recent_posts(RSS_FEEDS, hours=RSS_HOURS, max_per_feed=30)
  rss_content = format_posts_for_prompt(rss_posts, hours=RSS_HOURS)

  print("\nFetching non-RSS sources (pre-scrape)...")
  other_sources_content = fetch_other_sources_for_prompt(OTHER_SOURCES, OTHER_SOURCE_MAX_CHARS)

  recent_newsletters_text = load_recent_newsletters_for_prompt(DATA_DIR, RECENT_NEWSLETTERS_TO_INCLUDE)
  reference_html = load_reference_newsletter(DATA_DIR, REFERENCE_NEWSLETTER_FILE)

  prompt = f"""You are a personalized newsletter curator.

TODAY'S DATE: {day_of_week}, {current_date}

{PROMPT}

=== RECENT POSTS FROM RSS FEEDS (last {RSS_HOURS} hours) ===
{rss_content}

=== OTHER SOURCES (PRE-SCRAPED CONTENT) ===
{other_sources_content}

=== RECENT NEWSLETTERS (last {RECENT_NEWSLETTERS_TO_INCLUDE} newsletters to avoid repeating information) ===
{recent_newsletters_text}

=== REFERENCE NEWSLETTER (USE THIS FORMAT/STYLE) ===
<reference_newsletter>
{reference_html}
</reference_newsletter>

RESEARCH INSTRUCTIONS:
1. Review the RSS feed posts above and the pre-scraped other sources content above.
2. If you need more detail, you should call scrape_webpage / search_web / ask_perplexity for specific followups.
3. Your research should be VERY comprehensive, but the output should be VERY brief and skimmable.
4. ONLY include things from the past 24-48 hours.
5. Do NOT repeat items already covered in <recent_newsletters>. If something is still important, mention only a very short update and link the new source.

HTML OUTPUT:
- Title: "{NEWSLETTER_NAME} - {day_of_week}, {current_date}"
- Bulleted list broken into sections, very information dense, very concise. Only the most important things.
- EACH bullet MUST include link(s) to the source AND mention which source (e.g. "Zvi", "Transformer News") with hyperlink
- Most important items at the TOP
- Keep it brief: ~40 lines max, fewer if slow news day. Don't pad with old news.
- Use a two-column layout with CSS grid or flexbox, max page width ~900px centered
- Use <h1> for title, <h2> for section headers, <ul>/<li> for items
- No emojis! Use inline SVG icons instead. Use these to make the newsletter more visually interesting.
- Use <mark> around 3-8 key phrases total for the most important parts (not everywhere)
- Use text-fragment URL highlighting when warranted (the #:~:text=... URL parameter)
- Include basic inline CSS for the layout (max-width, columns, padding, readable font). Keep it simple and readable.
- DO NOT wrap in markdown code fences - output raw HTML only, starting with <!DOCTYPE html>

IMAGES:
- For 2-4 of the most visually interesting stories, include an image from the article
- Look inside the article content for compelling images - screenshots, diagrams, product photos, charts, etc.
- Prefer images that show what the story is about (e.g. a screenshot of a new AI feature, a chart from a research paper)
- Embed images using <img src="..." style="max-width: 200px; float: right; margin: 0 0 10px 10px; border-radius: 4px;">
- Skip logos, icons, author headshots, and generic stock photos
- If you can't find a good image for a story, skip it - don't force it
"""

  print("-" * 40)
  print(prompt)
  print("-" * 40)
  return prompt


async def generate_newsletter(test_mode=False, send_email=False):
  model = TEST_MODEL if test_mode else MODEL
  recipients = RECIPIENT_EMAIL if isinstance(RECIPIENT_EMAIL, list) else [RECIPIENT_EMAIL]
  print(f"\n{'='*60}")
  print(f"Generating {NEWSLETTER_NAME}")
  print(f"Date: {datetime.now().strftime('%A, %B %d, %Y')}")
  print(f"Model: {model}" + (" [TEST MODE]" if test_mode else ""))
  if send_email:
    print(f"Sending to: {', '.join(recipients)}")
  else:
    print("Email: Not sending")
  print(f"{'='*60}\n")

  prompt = build_prompt()
  model_settings = ModelSettings(parallel_tool_calls=True)

  agent = Agent(
    name="newsletter_agent",
    instructions=prompt,
    tools=ALL_TOOLS,
    model=model,
    default_max_turns=30,
    default_model_settings=model_settings,
  )

  print("Starting agent...")
  print("-" * 40)

  newsletter_content = ""
  stream = agent.stream("Generate today's newsletter based on the configured sources and interests.")

  async for event in stream:
    if event.kind == "message_delta" and event.text:
      print(event.text, end='', flush=True)
      newsletter_content += event.text
    elif event.kind == "tool_call":
      print(f"\n[Calling: {event.tool_name}]", flush=True)

  print("\n" + "-" * 40)
  newsletter_content = stream.final_output or newsletter_content
  return newsletter_content


async def main():
  parser = argparse.ArgumentParser(description="Generate a personalized AI newsletter")
  parser.add_argument('--send-email', action='store_true', help='Send the newsletter via email')
  parser.add_argument('--no-open', action='store_true', help='Do not open in browser')
  parser.add_argument('--test', action='store_true', help='Use cheaper test model (claude-haiku-4.5)')
  args = parser.parse_args()

  content = await generate_newsletter(test_mode=args.test, send_email=args.send_email)

  if not content:
    print("\nERROR: No content generated")
    sys.exit(1)

  content = clean_html_output(content)
  content = append_footer(content)

  if args.test:
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
      f.write(content)
      filepath = Path(f.name)
    print(f"\n[TEST MODE] Saved to temp file: {filepath}")
  else:
    current_date = datetime.now().strftime("%Y-%m-%d")
    filepath = save_newsletter(DATA_DIR, content, current_date)
    print(f"\nSaved to: {filepath}")

  if not args.no_open:
    print("Opening in browser...")
    open_in_browser(filepath)

  if args.send_email:
    if not RECIPIENT_EMAIL:
      print("ERROR: RECIPIENT_EMAIL not set in config.py")
      sys.exit(1)
    subject = f"{NEWSLETTER_NAME} - {datetime.now().strftime('%B %d, %Y')}"
    recipients = RECIPIENT_EMAIL if isinstance(RECIPIENT_EMAIL, list) else [RECIPIENT_EMAIL]
    all_sent = True
    for email in recipients:
      if send_email(subject, content, email):
        print(f"\nNewsletter sent to {email}")
      else:
        print(f"\nFailed to send email to {email}")
        all_sent = False
    if not all_sent:
      sys.exit(1)


if __name__ == "__main__":
  import platform
  if platform.system() == "Darwin":
    import asyncio.selector_events
    asyncio.selector_events._SelectorSocketTransport.__del__ = lambda self: None
  asyncio.run(main())

