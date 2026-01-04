# AI Newsletter Generator

Automated personalized AI newsletter using an LLM agent with web search tools.

## Quick Start

```bash
# Copy and customize config
cp config.template.py config.py

# Create .env with your API keys (see Environment Variables below)

# Run
./run.sh
```

## Commands

```bash
# Run directly
./run.sh

# Run without sending email (just generate and open)
python generate.py

# Run with cheaper test model
python generate.py --test
```

## macOS LaunchAgent (Optional)

To run automatically every morning, create a LaunchAgent plist at `~/Library/LaunchAgents/com.yourname.newsletter.plist`.

```bash
# Run manually via launchd
launchctl start org.jesenator.newsletter

# View logs
tail -f ~/Library/Logs/jesenator-newsletter.log
tail -f ~/Library/Logs/jesenator-newsletter-error.log

# Reload after editing plist
launchctl unload ~/Library/LaunchAgents/org.jesenator.newsletter.plist
launchctl load ~/Library/LaunchAgents/org.jesenator.newsletter.plist

# Check if loaded
launchctl list | grep jesenator
```

## Configuration

Copy `config.template.py` to `config.py` and customize:
- `NEWSLETTER_NAME` - title of newsletter
- `RECIPIENT_EMAIL` / `FROM_EMAIL` - email addresses
- `MODEL` / `TEST_MODEL` - which AI models to use
- `RSS_HOURS` - how far back to look for posts
- `RSS_FEEDS` - list of RSS feeds to monitor
- `OTHER_SOURCES` - non-RSS sites to scrape
- `PROMPT` - what you want in the newsletter

`config.py` is gitignored so your personal preferences stay private.

## Environment Variables

Stored in `.env`:
- `OPENROUTER_API_KEY` - for AI model access
- `SERPER_API_KEY` - for web search/scraping
- `SENDGRID_API_KEY` - for sending email

## Output

Generated newsletters saved to `data/newsletter_YYYY-MM-DD.html`

