"""
Template for your personalized newsletter config.

Copy this file to config.py and customize it for your interests.
config.py is gitignored so your personal preferences stay private.
"""

NEWSLETTER_NAME = "My Daily Newsletter"
RECIPIENT_EMAIL = "you@example.com"  # Can also be a list: ["a@example.com", "b@example.com"]
FROM_EMAIL = "newsletter@example.com"
REPLY_TO_EMAIL = ""  # Optional: email address for replies (defaults to FROM_EMAIL if empty)
MODEL = "anthropic/claude-opus-4.5" # any openrouter-compatible model should work
RSS_HOURS = 48
RECENT_NEWSLETTERS_TO_INCLUDE = 7
OTHER_SOURCE_MAX_CHARS = 20000
REFERENCE_NEWSLETTER_FILE = ""  # Optional: filename in data/ to use as format reference (full HTML)

SOURCES = [
  # Add URLs here - RSS feeds are auto-detected, others are scraped
  # "https://example.com/feed.xml",
  # "https://news.ycombinator.com",
]

PROMPT = """
I would like a daily summary of the latest and most important happenings in [YOUR FIELD/INTERESTS].

BACKGROUND: [Brief description of who you are and what you do]

## Priority ranking (highest to lowest):
1. [Most important topic]
2. [Second most important]
3. [Third most important]
4. [Fourth most important]
5. Everything else

## Also interested in:
- [Topic 1]
- [Topic 2]
- [Topic 3]
- [Add more as needed]

## Examples of things I would want to know:
- [Example 1]
- [Example 2]
- [Example 3]

## DO NOT include:
- [Things you don't care about]
- [More exclusions]
"""

