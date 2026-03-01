# AI Newsletter Generator

Automated personalized AI newsletter using an LLM agent with web search tools. Configuration is stored in a Notion database. Runs daily via GitHub Actions.

## Setup

1. Fork/clone this repo
2. Add secrets in GitHub: **Settings > Secrets and variables > Actions**:
   - `OPENROUTER_API_KEY` - for AI model access
   - `SERPER_API_KEY` - for web search/scraping
   - `SENDGRID_API_KEY` - for sending email
   - `NOTION_API_KEY` - for Notion database access
   - `NOTION_DATABASE_ID` - ID of the newsletters database
   - `NOTION_SUBSCRIBERS_DB_ID` - ID of the subscribers database
   - `FROM_EMAIL` - sender address
   - `REPLY_TO_EMAIL` - reply-to address
3. The workflow runs daily at 7 AM PST. You can also trigger it manually from the Actions tab.

## Local Development

```bash
# Create .env with the same keys listed above
pip install -r requirements.txt

python main.py                # Generate only (no email)
python main.py --open         # Generate and open in browser
python main.py --test         # Run newsletters with Test status
python main.py --send-email   # Generate and send emails
python main.py --just <ID>    # Run a single newsletter by ID
```

## Configuration

Newsletter configuration is stored in a Notion database. Each row represents a newsletter with:
- **Name** - title of the newsletter
- **Status** - Active, Paused, or Test (only active newsletters are sent)
- **Model** - which AI model to use
- **Sources** - line-separated list of RSS feeds and URLs
- **Page body** - the prompt describing what you want

Subscribers are managed in a linked Notion database with Name, Email, and subscription status.

General settings in `config.py`:
- `RSS_HOURS` - how far back to look for RSS posts
- `RECENT_NEWSLETTERS_TO_INCLUDE` - number of past newsletters to check for duplicates
- `REFERENCE_NEWSLETTER_FILE` - optional HTML file to use as format reference

## Output

Generated newsletters saved to `data/{newsletter_id}/newsletter_YYYY-MM-DD.html`
