# AI Newsletter Generator

Automated personalized AI newsletter using an LLM agent with web search tools. Configuration is stored in a Notion database.

## Quick Start

```bash
# Create .env with your API keys (see Environment Variables below)
# Run
./run.sh
```

## Commands

```bash
# Generate only (no email)
python main.py

# Generate and open in browser
python main.py --open

# Run with cheaper test model
python main.py --test

# Generate and send emails
python main.py --send-email
```

## Configuration

Newsletter configuration is stored in a Notion database. Each row represents a newsletter with:
- **Name** - title of the newsletter
- **Status** - Active or Paused (only Active newsletters are sent)
- **Model** - which AI model to use
- **Sources** - line-separated list of RSS feeds and URLs
- **Page body** - the prompt describing what you want

Subscribers are managed in a linked Notion database with Name, Email, and subscription status.

General settings in `config.py`:
- `FROM_EMAIL` / `REPLY_TO_EMAIL` - sender email addresses
- `TEST_MODEL` - cheaper model for testing
- `RSS_HOURS` - how far back to look for posts

## Environment Variables

Stored in `.env`:
- `OPENROUTER_API_KEY` - for AI model access
- `SERPER_API_KEY` - for web search/scraping
- `SENDGRID_API_KEY` - for sending email
- `NOTION_API_KEY` - for Notion database access
- `NOTION_DATABASE_ID` - ID of the newsletters database
- `NOTION_SUBSCRIBERS_DB_ID` - ID of the subscribers database

## Output

Generated newsletters saved to `data/{newsletter_id}/newsletter_YYYY-MM-DD.html`
