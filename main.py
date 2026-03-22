#!/usr/bin/env python3
"""
Newsletter Generator - Main entry point.

Usage:
  python main.py
  python main.py --test
  python main.py --open
  python main.py --send-email
  python main.py --just <page_id>
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from logger import log_info, log_error, log_warning, log_run_start, log_run_end, log_email

from generate import (
  generate_newsletter_for_config,
  get_newsletter_data_dir,
  send_email,
  append_footer,
)
from utils import clean_html_output, open_in_browser, save_newsletter, now_pacific
from notion import fetch_newsletters, update_log, format_log_entry
from config import CADENCE, DEFAULT_CADENCE

def should_run_today(cadence: str) -> bool:
  if cadence == "Weekly":
    return now_pacific().weekday() == 0  # Monday
  return True


def print_overview(newsletters, send_email: bool, test_mode: bool):
  print(f"\n{'='*60}")
  print(f"NEWSLETTER OVERVIEW - {now_pacific().strftime('%A, %B %d, %Y')}")
  print(f"{'='*60}")
  status = "Test" if test_mode else "Active"
  print(f"Found {len(newsletters)} {status.lower()} newsletter(s):\n")
  for i, nl in enumerate(newsletters, 1):
    folder_id = nl.page_id.replace('-', '')
    print(f"{i}. {nl.name}")
    print(f"   Cadence: {nl.cadence}")
    print(f"   Model: {nl.model}")
    print(f"   Sources: {len(nl.sources)}")
    print(f"   Folder: data/{folder_id}/")
    print(f"   Recipients ({len(nl.emails)}):")
    for email in nl.emails:
      print(f"     - {email}")
    # print(f"   Prompt: \n\n{'-'*40}\n{nl.prompt}\n\n{'-'*40}\n\n")
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
  parser.add_argument('--just', metavar='ID', help='Only run the newsletter with this ID (page_id)')
  args = parser.parse_args()

  status = 'Test' if args.test else 'Active'
  if args.just:
    print(f"Fetching newsletter {args.just} from Notion...")
    newsletters = fetch_newsletters(status=None)
    target_id = args.just.replace('-', '')
    newsletters = [nl for nl in newsletters if nl.page_id.replace('-', '') == target_id]
    if not newsletters:
      print(f"No newsletter found with ID: {args.just}")
      sys.exit(1)
  else:
    print(f"Fetching {status.lower()} newsletters from Notion...")
    newsletters = fetch_newsletters(status)
  
  if not newsletters:
    msg = f"No {status.lower()} newsletters found in Notion database."
    print(msg)
    log_info(msg)
    sys.exit(0)
  
  mode = f"{'send_email' if args.send_email else 'dry_run'}, {'test' if args.test else 'active'}"
  log_run_start(len(newsletters), mode)
  print_overview(newsletters, args.send_email, args.test)
  
  skip_cadence = args.just or args.test
  for newsletter_config in newsletters:
    if not skip_cadence and not should_run_today(newsletter_config.cadence):
      msg = f"Skipping {newsletter_config.name} ({newsletter_config.cadence} cadence, not scheduled today)"
      print(f"\n{msg}")
      log_info(msg)
      continue

    log_info(f"Starting generation for: {newsletter_config.name}")
    try:
      content, cost = await generate_newsletter_for_config(newsletter_config)
    except Exception as e:
      log_error(f"Generation failed for {newsletter_config.name}", e)
      print(f"\nERROR: Generation failed for {newsletter_config.name}: {e}")
      continue
    
    if not content:
      msg = f"No content generated for {newsletter_config.name}"
      print(f"\nERROR: {msg}")
      log_error(msg)
      continue

    content = clean_html_output(content)
    content = append_footer(content)

    newsletter_data_dir = get_newsletter_data_dir(newsletter_config)
    current_date = now_pacific().strftime("%Y-%m-%d")
    filepath = save_newsletter(newsletter_data_dir, content, current_date)
    print(f"\nSaved to: {filepath}")
    log_info(f"Saved newsletter to: {filepath}")

    if args.open:
      print("Opening in browser...")
      open_in_browser(filepath)

    sent_emails = []
    if args.send_email:
      if not newsletter_config.emails:
        msg = f"No subscribers for {newsletter_config.name}"
        print(f"WARNING: {msg}")
        log_warning(msg)
      else:
        subject = f"{newsletter_config.name} - {now_pacific().strftime('%B %d, %Y')}"
        for email in newsletter_config.emails:
          if send_email(subject, content, email):
            print(f"Newsletter sent to {email}")
            sent_emails.append(email)
            log_email(email, True)
          else:
            print(f"Failed to send email to {email}")
            log_email(email, False, "send_email returned False")
    
    # Update the log in Notion
    log_entry = format_log_entry(sent_emails if args.send_email else [], cost=cost)
    update_log(newsletter_config.page_id, log_entry)
    print(f"Updated Notion log: {log_entry}")
    log_info(f"Updated Notion log for {newsletter_config.name}: {log_entry}")
  
  log_run_end()


if __name__ == "__main__":
  import platform
  if platform.system() == "Darwin":
    # Suppress harmless cleanup errors on macOS (SSL and socket transports)
    import asyncio.selector_events
    import asyncio.sslproto
    asyncio.selector_events._SelectorSocketTransport.__del__ = lambda self: None
    # Patch SSL protocol to suppress cleanup errors
    _orig_ssl_del = getattr(asyncio.sslproto.SSLProtocol, '__del__', None)
    def _silent_ssl_del(self):
      try:
        if _orig_ssl_del:
          _orig_ssl_del(self)
      except Exception:
        pass
    asyncio.sslproto.SSLProtocol.__del__ = _silent_ssl_del
  
  if sys.version_info >= (3, 10):
    asyncio.run(main())
  else:
    # Python 3.9 has issues with event loop cleanup on macOS
    loop = asyncio.new_event_loop()
    try:
      loop.run_until_complete(main())
    finally:
      # Give pending tasks time to clean up
      loop.run_until_complete(asyncio.sleep(0.5))
      # Cancel remaining tasks gracefully
      pending = asyncio.all_tasks(loop)
      for task in pending:
        task.cancel()
      if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
      loop.close()
