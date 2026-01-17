"""Notion integration for Newsletter Generator."""

from __future__ import annotations
import os
import httpx
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

def get_headers():
  return {
    'Authorization': f'Bearer {os.getenv("NOTION_API_KEY")}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
  }

@dataclass
class NewsletterConfig:
  page_id: str
  name: str
  model: str
  sources: list[str]
  emails: list[str]
  prompt: str

def extract_plain_text(rich_text_list: list) -> str:
  return ''.join(item.get('plain_text', '') for item in rich_text_list)

def parse_sources(rich_text_list: list) -> list[str]:
  text = extract_plain_text(rich_text_list)
  lines = [line.strip() for line in text.split('\n') if line.strip()]
  return [line for line in lines if line.startswith('http')]

def fetch_page_content(page_id: str) -> str:
  """Fetch all blocks from a page and convert to plain text prompt."""
  headers = get_headers()
  blocks = []
  cursor = None
  
  while True:
    url = f'https://api.notion.com/v1/blocks/{page_id}/children?page_size=100'
    if cursor:
      url += f'&start_cursor={cursor}'
    resp = httpx.get(url, headers=headers, timeout=30)
    data = resp.json()
    blocks.extend(data.get('results', []))
    if not data.get('has_more'):
      break
    cursor = data.get('next_cursor')
  
  lines = []
  for block in blocks:
    block_type = block.get('type')
    content = block.get(block_type, {})
    rich_text = content.get('rich_text', [])
    text = extract_plain_text(rich_text)
    
    if block_type == 'heading_1':
      lines.append(f'\n# {text}')
    elif block_type == 'heading_2':
      lines.append(f'\n## {text}')
    elif block_type == 'heading_3':
      lines.append(f'\n### {text}')
    elif block_type == 'bulleted_list_item':
      lines.append(f'- {text}')
    elif block_type == 'numbered_list_item':
      lines.append(f'1. {text}')
    elif block_type == 'paragraph' and text:
      lines.append(text)
    elif block_type == 'divider':
      lines.append('---')
  
  return '\n'.join(lines)

def fetch_subscribers_for_newsletter(newsletter_page_id: str) -> list[str]:
  """Fetch email addresses of subscribed users for a newsletter.
  
  Handles subscribe/unsubscribe by checking the most recent form submission per email.
  """
  headers = get_headers()
  
  # Fetch all entries for this newsletter, sorted by created time descending
  resp = httpx.post(
    f'https://api.notion.com/v1/databases/{os.getenv("NOTION_SUBSCRIBERS_DB_ID")}/query',
    headers=headers,
    json={
      'filter': {
        'property': 'Newsletter',
        'relation': {'contains': newsletter_page_id}
      },
      'sorts': [{'timestamp': 'created_time', 'direction': 'descending'}]
    },
    timeout=30
  )
  data = resp.json()
  
  # Track most recent status per email (first seen = most recent due to sort)
  email_status: dict[str, str] = {}
  for page in data.get('results', []):
    props = page.get('properties', {})
    email = props.get('Email', {}).get('email')
    status_select = props.get('Status', {}).get('select')
    status = status_select.get('name') if status_select else None
    
    if email and email not in email_status:
      email_status[email] = status
  
  # Return only emails whose most recent status is Subscribe
  return [email for email, status in email_status.items() if status == 'Subscribe']

def fetch_newsletters(status: str = 'Active') -> list[NewsletterConfig]:
  """Fetch all newsletters with the given Status."""
  headers = get_headers()
  
  resp = httpx.post(
    f'https://api.notion.com/v1/databases/{os.getenv("NOTION_DATABASE_ID")}/query',
    headers=headers,
    json={
      'filter': {
        'property': 'Status',
        'select': {'equals': status}
      }
    },
    timeout=30
  )
  data = resp.json()
  
  newsletters = []
  for page in data.get('results', []):
    page_id = page['id']
    props = page.get('properties', {})
    
    name = extract_plain_text(props.get('Name', {}).get('title', []))
    model_select = props.get('Model', {}).get('select')
    model = model_select.get('name') if model_select else 'anthropic/claude-opus-4.5'
    sources = parse_sources(props.get('Sources', {}).get('rich_text', []))
    emails = fetch_subscribers_for_newsletter(page_id)
    prompt = fetch_page_content(page_id)
    
    newsletters.append(NewsletterConfig(
      page_id=page_id,
      name=name,
      model=model,
      sources=sources,
      emails=emails,
      prompt=prompt,
    ))
  
  return newsletters

def update_log(page_id: str, log_entry: str) -> bool:
  """Prepend a log entry to the Log field of a newsletter page."""
  headers = get_headers()
  
  # First get current log content
  resp = httpx.get(f'https://api.notion.com/v1/pages/{page_id}', headers=headers, timeout=30)
  data = resp.json()
  current_log = extract_plain_text(data.get('properties', {}).get('Log', {}).get('rich_text', []))
  
  # Prepend new entry
  new_log = f"{log_entry}\n{current_log}".strip()
  
  # Update the page
  resp = httpx.patch(
    f'https://api.notion.com/v1/pages/{page_id}',
    headers=headers,
    json={
      'properties': {
        'Log': {
          'rich_text': [{'type': 'text', 'text': {'content': new_log[:2000]}}]
        }
      }
    },
    timeout=30
  )
  if resp.status_code != 200:
    print(f"WARNING: Failed to update Notion log: {resp.status_code} - {resp.json().get('message', 'Unknown error')}")
    return False
  return True

def format_log_entry(sent_to: list[str], cost: Optional[float] = None) -> str:
  """Format a log entry with timestamp and details."""
  now = datetime.now().strftime('%Y-%m-%d %I:%M %p')
  count = len(sent_to)
  recipient_str = f"{count} recipient" if count == 1 else f"{count} recipients"
  if cost is not None:
    return f"[{now}] Sent to {recipient_str}. Cost: ${cost:.2f}"
  return f"[{now}] Sent to {recipient_str}"
