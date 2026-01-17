"""
General config for the newsletter generator.
Newsletter-specific settings (model, sources, prompt, recipients) are in Notion.
"""

FROM_EMAIL = "newsletter@example.com"
REPLY_TO_EMAIL = ""  # Optional: email address for replies (defaults to FROM_EMAIL if empty)
TEST_MODEL = "anthropic/claude-haiku-4.5"
RSS_HOURS = 28
RECENT_NEWSLETTERS_TO_INCLUDE = 7
OTHER_SOURCE_MAX_CHARS = 20000
REFERENCE_NEWSLETTER_FILE = "newsletter_reference.html"  # In data/ folder
