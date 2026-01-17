#!/usr/bin/env python3
"""
Newsletter Generator - Main entry point.

Usage:
  python main.py
  python main.py --test
  python main.py --open
  python main.py --send-email
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from generate import (
  generate_newsletter_for_config,
  get_newsletter_data_dir,
  send_email,
  append_footer,
)
from utils import clean_html_output, open_in_browser, save_newsletter
from notion import fetch_newsletters, update_log, format_log_entry


def print_overview(newsletters, send_email: bool, test_mode: bool):
  print(f"\n{'='*60}")
  print(f"NEWSLETTER OVERVIEW - {datetime.now().strftime('%A, %B %d, %Y')}")
  print(f"{'='*60}")
  status = "Test" if test_mode else "Active"
  print(f"Found {len(newsletters)} {status.lower()} newsletter(s):\n")
  for i, nl in enumerate(newsletters, 1):
    folder_id = nl.page_id.replace('-', '')
    print(f"{i}. {nl.name}")
    print(f"   Model: {nl.model}")
    print(f"   Sources: {len(nl.sources)}")
    print(f"   Folder: data/{folder_id}/")
    print(f"   Recipients ({len(nl.emails)}):")
    for email in nl.emails:
      print(f"     - {email}")
    print()
  print(f"{'='*60}")
  if send_email:
    print("MODE: Will send emails")
  else:
    print("MODE: Dry run (no emails will be sent)")
  if test_mode:
    print("STATUS: Running newsletters with 'Test' status")
  print(f"{'='*60}\n")


async def main():
  parser = argparse.ArgumentParser(description="Generate personalized AI newsletters from Notion config")
  parser.add_argument('--send-email', action='store_true', help='Actually send the newsletter via email')
  parser.add_argument('--open', action='store_true', help='Open in browser after generating')
  parser.add_argument('--test', action='store_true', help='Run newsletters with Test status instead of Active')
  args = parser.parse_args()

  status = 'Test' if args.test else 'Active'
  print(f"Fetching {status.lower()} newsletters from Notion...")
  newsletters = fetch_newsletters(status)
  
  if not newsletters:
    print(f"No {status.lower()} newsletters found in Notion database.")
    sys.exit(0)
  
  print_overview(newsletters, args.send_email, args.test)
  
  for newsletter_config in newsletters:
    content = await generate_newsletter_for_config(newsletter_config)
    
    if not content:
      print(f"\nERROR: No content generated for {newsletter_config.name}")
      continue

    content = clean_html_output(content)
    content = append_footer(content)

    newsletter_data_dir = get_newsletter_data_dir(newsletter_config)
    current_date = datetime.now().strftime("%Y-%m-%d")
    filepath = save_newsletter(newsletter_data_dir, content, current_date)
    print(f"\nSaved to: {filepath}")

    if args.open:
      print("Opening in browser...")
      open_in_browser(filepath)

    sent_emails = []
    if args.send_email:
      if not newsletter_config.emails:
        print(f"WARNING: No subscribers for {newsletter_config.name}")
      else:
        subject = f"{newsletter_config.name} - {datetime.now().strftime('%B %d, %Y')}"
        for email in newsletter_config.emails:
          if send_email(subject, content, email):
            print(f"Newsletter sent to {email}")
            sent_emails.append(email)
          else:
            print(f"Failed to send email to {email}")
    
    # Update the log in Notion
    log_entry = format_log_entry(sent_emails if args.send_email else [], cost=None)
    if not args.test:
      update_log(newsletter_config.page_id, log_entry)
      print(f"Updated Notion log: {log_entry}")


if __name__ == "__main__":
  import platform
  if platform.system() == "Darwin":
    import asyncio.selector_events
    asyncio.selector_events._SelectorSocketTransport.__del__ = lambda self: None
  
  if sys.version_info >= (3, 10):
    asyncio.run(main())
  else:
    # Python 3.9 has issues with event loop cleanup on macOS
    loop = asyncio.new_event_loop()
    try:
      loop.run_until_complete(main())
    finally:
      # Give pending tasks time to clean up
      loop.run_until_complete(asyncio.sleep(0.25))
      loop.close()
