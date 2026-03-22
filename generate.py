"""Newsletter generation functions."""

import os
from pathlib import Path

from agents import ModelSettings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, ReplyTo

from agent import Agent
from tools import ALL_TOOLS
from feeds import fetch_all_sources, format_sources_for_prompt, parse_twitter_url
from twitter import TwitterClient, format_tweets_xml
from utils import load_recent_newsletters_for_prompt, load_reference_newsletter, now_pacific
from notion import NewsletterConfig
from config import (
  RSS_HOURS,
  RECENT_NEWSLETTERS_TO_INCLUDE, OTHER_SOURCE_MAX_CHARS,
  REFERENCE_NEWSLETTER_FILE,
)
from logger import log_info, log_error, log_prompt, log_generation

DATA_DIR = Path(__file__).parent / "data"

FOOTER_HTML = '''
<footer style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e5e5; font-size: 12px; color: #666; text-align: center; line-height: 1.8;">
  Made by <a href="https://jessewgilbert.com" style="color: #666;">jessewgilbert.com</a> · <a href="https://www.notion.so/jessegilbert/Personalized-AI-Newsletter-Dashboard-Beta-2de49c95bdef803c90c9f2515356e277" style="color: #666;">Newsletter Dashboard</a><br>
  Reply to unsubscribe, give feedback, or request a personalized AI newsletter for yourself or a friend.
</footer>
'''

def append_footer(html_content: str) -> str:
  if '</body>' in html_content:
    return html_content.replace('</body>', FOOTER_HTML + '</body>')
  return html_content + FOOTER_HTML

def send_email(subject: str, html_content: str, to_email: str):
  api_key = os.getenv('SENDGRID_API_KEY')
  if not api_key:
    log_error("SENDGRID_API_KEY not set")
    print("ERROR: SENDGRID_API_KEY not set")
    return False

  from_email = os.getenv('FROM_EMAIL')
  reply_to_email = os.getenv('REPLY_TO_EMAIL')

  message = Mail(
    from_email=from_email,
    to_emails=to_email,
    subject=subject,
    html_content=html_content
  )
  if reply_to_email:
    message.reply_to = ReplyTo(reply_to_email)

  try:
    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    print(f"Email sent! Status: {response.status_code}")
    log_info(f"Email sent to {to_email}, status={response.status_code}")
    return True
  except Exception as e:
    log_error(f"Failed to send email to {to_email}", e)
    print(f"ERROR sending email: {e}")
    return False


def get_newsletter_data_dir(newsletter_config: NewsletterConfig) -> Path:
  """Get the data directory for a specific newsletter (by page ID without dashes)."""
  folder_id = newsletter_config.page_id.replace('-', '')
  newsletter_dir = DATA_DIR / folder_id
  newsletter_dir.mkdir(parents=True, exist_ok=True)
  return newsletter_dir

def build_prompt(newsletter_config: NewsletterConfig):
  now = now_pacific()
  current_date = now.strftime("%B %d, %Y")
  day_of_week = now.strftime("%A")
  newsletter_name = newsletter_config.name
  newsletter_data_dir = get_newsletter_data_dir(newsletter_config)

  rss_urls = []
  twitter_profiles = []
  twitter_lists = []
  for url in newsletter_config.sources:
    tw = parse_twitter_url(url)
    if tw and tw[0] == 'profile':
      twitter_profiles.append(tw[1])
    elif tw and tw[0] == 'list':
      twitter_lists.append(tw[1])
    else:
      rss_urls.append(url)

  print(f"\nFetching sources (last {RSS_HOURS} hours)...")
  print(f"  RSS/scrape URLs: {len(rss_urls)}, Twitter profiles: {len(twitter_profiles)}, Twitter lists: {len(twitter_lists)}")
  sources_data = fetch_all_sources(rss_urls, hours=RSS_HOURS, max_per_feed=30, max_scrape_chars=OTHER_SOURCE_MAX_CHARS)
  sources_content = format_sources_for_prompt(sources_data, hours=RSS_HOURS)

  twitter_content = ""
  if twitter_profiles or twitter_lists:
    try:
      client = TwitterClient()
      raw_tweets = client.fetch_all(twitter_profiles, twitter_lists, hours=RSS_HOURS)
      filtered_tweets = client.filter_tweets(raw_tweets)
      twitter_content = format_tweets_xml(filtered_tweets)
      print(f"[Twitter] {len(raw_tweets)} raw -> {len(filtered_tweets)} filtered tweets")
    except Exception as e:
      print(f"[Twitter] Error fetching tweets: {e}")
      log_error("[Twitter] Error fetching tweets", e)

  recent_newsletters_text = load_recent_newsletters_for_prompt(newsletter_data_dir, RECENT_NEWSLETTERS_TO_INCLUDE)
  reference_html = load_reference_newsletter(DATA_DIR, REFERENCE_NEWSLETTER_FILE)

  system_prompt = f"""You are a personalized newsletter creator.

TODAY'S DATE: {day_of_week}, {current_date}

=== USER INSTRUCTIONS on what they want to see in the newsletter. HONOR THESE INSTRUCTIONS CLOSELY ===
These should override any other instructions you may have.
<user_instructions_and_personalization>
{newsletter_config.prompt}
</user_instructions_and_personalization>

RESEARCH INSTRUCTIONS:
1. Review the RSS feed posts, tweets, and pre-scraped sources content provided.
2. If you need more detail, call scrape_webpage / search_web / ask_perplexity for specific followups.
3. Your research should be VERY comprehensive, but the output should be VERY brief and skimmable.
4. ONLY include things from the past {RSS_HOURS} hours that are NOT in recent newsletters.
5. CRITICAL ANTI-REPETITION RULE: If a story appeared in ANY recent newsletter, DO NOT include it unless there's a genuinely new development. When in doubt, leave it out.
  If the same story/topic was covered in any recent newsletter, you MUST either:
  a. SKIP IT ENTIRELY (preferred if no meaningful update)
  b. Include ONLY a brief "Update:" with the new information and link
6. WARNING: The user_instructions_and_personalization prompt for this newsletter may be different from that of previous newsletters (and is likely different from the prompt for the reference newsletter). Don't index to heavily on these, and make sure to follow the instructions closely when creating the newsletter.

HTML OUTPUT:
- Title: "{newsletter_name} - {day_of_week}, {current_date}" (use this EXACT title in both <title> and <h1> tags)
- Bulleted list broken into sections, very information dense, very concise. Only the most important things.
- EACH bullet MUST include link(s) to the source AND mention which source (e.g. "Zvi", "Transformer News") with hyperlink
- For Twitter/X sources, attribute as "X: <display name>" (e.g. "X: Jeffery Ladish", "X: Jim Fan")
- Most important items at the TOP
- Keep it brief: ~40 lines max, fewer if there's less news. It's BETTER to have a short newsletter.
- Use a two-column layout with CSS grid or flexbox, max page width ~900px centered
- Use <h1> for title, <h2> for section headers, <ul>/<li> for items
- No emojis! Use inline SVG icons instead. Use these to make the newsletter more visually interesting.
- Use <mark> around 3-8 key phrases total for the most important parts (not everywhere)
- Use text-fragment URL highlighting when warranted (the #:~:text=... URL parameter)
- Include basic inline CSS for the layout (max-width, columns, padding, readable font). Keep it simple and readable.
- DO NOT wrap in markdown code fences - output raw HTML only, starting with <!DOCTYPE html>
- Do NOT include anything already covered in recent newsletters (unless there's a meaningful update)
- Do NOT include any quote block or blurb at the end of the newsletter.
- Do NOT include a footer. No "Made by" links, no unsubscribe text, no dashboard links. The footer is added automatically by the system.

IMAGES:
- For 2-4 of the most visually interesting stories, include an image from the article
- Look inside the article content for compelling images - screenshots, diagrams, product photos, charts, etc.
- Prefer images that show what the story is about (e.g. a screenshot of a new AI feature, a chart from a research paper)
- Embed images using <img src="..." style="max-width: 200px; float: right; margin: 0 0 10px 10px; border-radius: 4px;">
- Skip logos, icons, author headshots, and generic stock photos
- If you can't find a good image for a story, skip it - don't force it

TO REITERATE:
- Keep the newsletter very brief and skimmable
- Don't repeat things that you already covered in previous newsletters
- Follow the user instructions <user_instructions_and_personalization> closely, those instructions can override any other instructions you may have.
"""

  user_prompt = f"""Generate a newsletter for today based on the user instructions.

TODAY'S DATE: {day_of_week}, {current_date}
=== SOURCES (RSS FEEDS + SCRAPED PAGES, last {RSS_HOURS} hours) ===
<sources>
{sources_content}
</sources>

=== TWITTER SOURCES (last {RSS_HOURS} hours) ===
<tweets>
{twitter_content}
</tweets>

=== RECENT NEWSLETTERS (last {RECENT_NEWSLETTERS_TO_INCLUDE}). CRITICAL: DO NOT REPEAT THESE ITEMS ===
<recent_newsletters>
{recent_newsletters_text}
</recent_newsletters>

=== REFERENCE NEWSLETTER (USE THIS FORMAT/STYLE) ===
<reference_newsletter>
{reference_html}
</reference_newsletter>
"""

  print("\033[94mSystem prompt:\033[0m")
  print("\033[94m" + "-" * 40 + "\033[0m")
  print("\033[96m" + system_prompt + "\033[0m")
  print("\033[94m" + "-" * 40 + "\033[0m")
  print("\033[93mUser prompt:\033[0m")
  print("\033[93m" + "-" * 40 + "\033[0m")
  print("\033[33m" + user_prompt + "\033[0m")
  print("\033[93m" + "-" * 40 + "\033[0m")

  log_prompt(f"SYSTEM PROMPT for {newsletter_config.name}", system_prompt)
  log_prompt(f"USER PROMPT for {newsletter_config.name}", user_prompt)
  return (system_prompt, user_prompt)


async def generate_newsletter_for_config(newsletter_config: NewsletterConfig):
  print(f"\n{'='*60}")
  print(f"Generating: {newsletter_config.name}")
  print(f"Date: {now_pacific().strftime('%A, %B %d, %Y')}")
  print(f"Model: {newsletter_config.model}")
  print(f"Sources: {len(newsletter_config.sources)} configured")
  print(f"{'='*60}\n")

  system_prompt, user_prompt = build_prompt(newsletter_config)
  model_settings = ModelSettings(
    parallel_tool_calls=True,
    extra_body={'reasoning': {'effort': 'medium'}},
  )

  agent = Agent(
    name="newsletter_agent",
    instructions=system_prompt,
    tools=ALL_TOOLS,
    model=newsletter_config.model,
    default_max_turns=30,
    default_model_settings=model_settings,
  )

  print("Starting agent...")
  print("-" * 40)
  log_info(f"Starting agent for {newsletter_config.name} with model {newsletter_config.model}")

  result = await agent.run(user_prompt)
  newsletter_content = result.final_output

  print(newsletter_content)
  print("-" * 40)

  agent.print_usage()
  cost = agent.get_cost()

  log_generation(f"GENERATED NEWSLETTER: {newsletter_config.name}", newsletter_content or "(empty)")
  return newsletter_content, cost
