"""Twitter API client for fetching tweets from profiles and lists."""

import os
import re
import json
import tweepy
from datetime import datetime, timedelta, timezone

from logger import log_info, log_error


TWEET_FIELDS = [
  "author_id", "referenced_tweets", "created_at", "entities",
  "note_tweet", "conversation_id", "attachments", "public_metrics",
]
USER_FIELDS = ["id", "name", "username", "profile_image_url"]
EXPANSIONS = [
  "author_id", "referenced_tweets.id",
  "referenced_tweets.id.author_id", "attachments.media_keys",
]
MEDIA_FIELDS = ["url", "preview_image_url"]


def resolve_all_urls(text: str, urls: list[dict]) -> str:
  for url_obj in urls:
    short = url_obj.get("short_url")
    expanded = url_obj.get("url", "")
    title = url_obj.get("title", "")
    if short and expanded and short in text:
      replacement = f"{expanded} [{title}]" if title else expanded
      text = text.replace(short, replacement)
    elif expanded and expanded in text and title:
      text = text.replace(expanded, f"{expanded} [{title}]", 1)
  text = re.sub(r'\s*https://t\.co/\w+', '', text)
  return text


def format_tweet_xml(tweet: dict) -> str:
  date_str = tweet.get("date", "")[:10] if tweet.get("date") else ""
  tweet_type = tweet.get("type", "original")
  attrs = f'id="{tweet["id"]}" user="{tweet.get("user", "")}" date="{date_str}" type="{tweet_type}"'

  if retweeters := tweet.get("retweeted_by"):
    users = " ".join(r.get("user", "") for r in retweeters if r.get("user"))
    if users:
      attrs += f' shared_by="{users}"'

  lines = [f"<tweet {attrs}>"]

  text = tweet.get("text", "")
  if urls := tweet.get("urls"):
    text = resolve_all_urls(text, urls)
  else:
    text = re.sub(r'\s*https://t\.co/\w+', '', text)
  lines.append(f"  <text>\n{text}\n  </text>")

  if ref := tweet.get("referenced"):
    ref_text = ref.get("text", "")
    if ref_urls := ref.get("urls"):
      ref_text = resolve_all_urls(ref_text, ref_urls)
    else:
      ref_text = re.sub(r'\s*https://t\.co/\w+', '', ref_text)
    lines.append(f'  <referenced user="{ref.get("user", "")}">{ref_text}</referenced>')

  if thread := tweet.get("thread_info", {}).get("thread_tweets"):
    lines.append("  <thread>")
    for t in thread[:3]:
      t_text = t.get("text", "")
      if thread_urls := t.get("urls"):
        t_text = resolve_all_urls(t_text, thread_urls)
      else:
        t_text = re.sub(r'\s*https://t\.co/\w+', '', t_text)
      lines.append(f"    <reply>{t_text}</reply>")
    lines.append("  </thread>")

  if metrics := tweet.get("metrics"):
    parts = " ".join(f'{k}="{v}"' for k, v in metrics.items())
    lines.append(f"  <metrics {parts} />")

  lines.append("</tweet>")
  return "\n".join(lines)


def format_tweets_xml(tweets: list[dict]) -> str:
  if not tweets:
    return ""
  lines = []
  for tweet in tweets:
    lines.append(format_tweet_xml(tweet))
    lines.append("")
  return "\n".join(lines)


class TwitterClient:

  def __init__(self):
    self._authed = False
    self._user_cache = {}

  def _auth(self):
    if self._authed:
      return
    token = os.getenv('TWITTER_BEARER_TOKEN')
    if not token:
      raise RuntimeError("TWITTER_BEARER_TOKEN not set")
    self.client = tweepy.Client(bearer_token=token)
    self._authed = True

  def get_user(self, username: str) -> dict:
    username = username.lstrip('@')
    if username in self._user_cache:
      return self._user_cache[username]
    self._auth()
    response = self.client.get_user(
      username=username,
      user_fields=USER_FIELDS,
    )
    if not response.data:
      raise ValueError(f"Twitter user not found: {username}")
    user = dict(response.data)
    self._user_cache[username] = user
    return user

  def _parse_response(self, tweet_response: tweepy.Response) -> list[dict]:
    if not tweet_response.data:
      return []
    users = tweet_response.includes.get("users", [])
    all_tweets = tweet_response.includes.get("tweets", [])

    user_map = {user["id"]: dict(user) for user in users}
    tweet_map = {
      tweet["id"]: json.loads(json.dumps(dict(tweet), default=str))
      for tweet in all_tweets
    }

    return [
      self._parse_tweet(tweet, user_map, tweet_map)
      for tweet in tweet_response.data
    ]

  def _parse_tweet(self, tweet, user_map: dict, tweet_map: dict) -> dict:
    res = dict(tweet)
    res["created_at"] = tweet["created_at"].isoformat()
    res["user"] = user_map.get(tweet["author_id"], None)

    if "referenced_tweets" in tweet:
      res["referenced_tweets"] = [
        {
          **dict(ref_tweet),
          "tweet": tweet_map.get(ref_tweet["id"])
        } for ref_tweet in tweet["referenced_tweets"]
      ]
      for ref_tweet in res["referenced_tweets"]:
        if ref_tweet["tweet"]:
          ref_tweet["tweet"]["user"] = user_map.get(
            ref_tweet["tweet"].get("author_id"), None
          )

    return res

  def get_user_tweets(self, username: str, hours: int) -> list[dict]:
    self._auth()
    user = self.get_user(username)
    user_id = user['id']
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=hours)

    print(f"[Twitter] Fetching tweets for @{username} (last {hours}h)...")
    log_info(f"[Twitter] Fetching tweets for @{username} (last {hours}h)")

    all_tweets = []
    pages = 0
    for response in tweepy.Paginator(
      self.client.get_users_tweets,
      user_id,
      max_results=100,
      start_time=start_time,
      end_time=now,
      tweet_fields=TWEET_FIELDS,
      user_fields=USER_FIELDS,
      expansions=EXPANSIONS,
      media_fields=MEDIA_FIELDS,
      limit=5,
    ):
      pages += 1
      if not response or not response.data:
        break
      if not response.includes:
        break
      parsed = self._parse_response(response)
      all_tweets.extend(parsed)
      print(f"[Twitter] @{username} page {pages}: {len(parsed)} tweets")

    print(f"[Twitter] @{username}: {len(all_tweets)} tweets total")
    log_info(f"[Twitter] @{username}: {len(all_tweets)} tweets")
    return all_tweets

  def get_list_tweets(self, list_id: str, hours: int) -> list[dict]:
    self._auth()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    print(f"[Twitter] Fetching tweets from list {list_id} (last {hours}h)...")
    log_info(f"[Twitter] Fetching tweets from list {list_id} (last {hours}h)")

    all_tweets = []
    pages = 0
    for response in tweepy.Paginator(
      self.client.get_list_tweets,
      id=list_id,
      tweet_fields=TWEET_FIELDS,
      user_fields=USER_FIELDS,
      expansions=EXPANSIONS,
      media_fields=MEDIA_FIELDS,
      limit=8,
    ):
      pages += 1
      if not response or not response.data or not response.includes:
        break

      parsed = self._parse_response(response)

      should_stop = False
      for tweet in parsed:
        tweet_date = datetime.fromisoformat(tweet['created_at']).astimezone(timezone.utc)
        if tweet_date < cutoff:
          print(f"[Twitter] List {list_id}: reached tweets older than cutoff, stopping")
          should_stop = True
          break
        all_tweets.append(tweet)

      if should_stop:
        break
      print(f"[Twitter] List {list_id} page {pages}: {len(parsed)} tweets")

    print(f"[Twitter] List {list_id}: {len(all_tweets)} tweets total")
    log_info(f"[Twitter] List {list_id}: {len(all_tweets)} tweets")
    return all_tweets

  def fetch_all(self, profiles: list[str], list_ids: list[str], hours: int) -> list[dict]:
    all_tweets = []
    for username in profiles:
      try:
        tweets = self.get_user_tweets(username, hours)
        all_tweets.extend(tweets)
      except Exception as e:
        print(f"[Twitter] Error fetching @{username}: {e}")
        log_error(f"[Twitter] Error fetching @{username}", e)
    for list_id in list_ids:
      try:
        tweets = self.get_list_tweets(list_id, hours)
        all_tweets.extend(tweets)
      except Exception as e:
        print(f"[Twitter] Error fetching list {list_id}: {e}")
        log_error(f"[Twitter] Error fetching list {list_id}", e)
    return all_tweets

  def filter_tweets(self, tweets: list[dict]) -> list[dict]:
    filtered = self._filter_retweets(tweets)
    filtered = self._filter_threads(filtered)
    return [self._filter_tweet(tweet) for tweet in filtered]

  def _filter_retweets(self, tweets: list[dict]) -> list[dict]:
    retweets = {}
    filtered = []

    for tweet in tweets:
      is_retweet = (
        "referenced_tweets" in tweet
        and tweet["referenced_tweets"][0]["type"] == "retweeted"
      )
      if is_retweet:
        retweet = tweet["referenced_tweets"][0]["tweet"]
        tid = tweet["id"]
        if tid not in retweets:
          retweets[tid] = {"tweet": retweet, "retweeted_by": []}
        author_tag = tweet.get("user", {}).get("username")
        retweets[tid]["retweeted_by"].append({
          "user": f"@{author_tag}" if author_tag else None,
          "date": tweet["created_at"]
        })
      else:
        filtered.append(tweet)

    for tweet in filtered:
      tid = tweet["id"]
      if tid in retweets:
        tweet["retweeted_by"] = retweets[tid]["retweeted_by"]
        del retweets[tid]

    for rt in retweets.values():
      if rt["tweet"]:
        rt["tweet"]["retweeted_by"] = rt["retweeted_by"]
        filtered.append(rt["tweet"])

    return filtered

  def _filter_threads(self, tweets: list[dict]) -> list[dict]:
    conversations = {}
    for tweet in tweets:
      cid = tweet.get("conversation_id")
      if not cid:
        continue
      tweet_date = datetime.fromisoformat(tweet["created_at"])
      if cid not in conversations:
        conversations[cid] = []
      conversations[cid].append({"tweet": tweet, "date": tweet_date})

    filtered = []
    processed = set()
    for tweet in tweets:
      cid = tweet.get("conversation_id")
      if not cid:
        filtered.append(tweet)
        continue
      if cid in processed:
        continue
      processed.add(cid)

      thread = conversations[cid]
      thread.sort(key=lambda x: x["date"])
      root = thread[0]["tweet"]
      if len(thread) > 1:
        root["thread_info"] = {
          "total_tweets": len(thread),
          "is_thread": True,
          "thread_tweets": [t["tweet"] for t in thread[1:]],
        }
      filtered.append(root)

    return filtered

  def _extract_urls_from_tweet(self, tweet: dict) -> list[dict]:
    urls = []
    tweet_urls = None
    if "note_tweet" in tweet and "entities" in tweet["note_tweet"]:
      tweet_urls = tweet["note_tweet"].get("entities", {}).get("urls")
    if tweet_urls is None:
      tweet_urls = tweet.get("entities", {}).get("urls")
    if tweet_urls is None:
      return urls

    for url in tweet_urls:
      final_url = url.get("unwound_url", url.get("expanded_url", url.get("url")))
      if final_url and ("/photo/" in final_url or "/video/" in final_url):
        continue
      url_obj = {"url": final_url}
      short_url = url.get("url")
      if short_url and short_url != final_url:
        url_obj["short_url"] = short_url
      if "description" in url:
        url_obj["description"] = url["description"]
      if "title" in url:
        url_obj["title"] = url["title"]
      urls.append(url_obj)

    return urls

  def _filter_tweet(self, tweet: dict) -> dict:
    text = tweet.get("note_tweet", tweet).get("text")
    author_tag = tweet.get("user", {}).get("username")
    tweet_type = "original"
    referenced = None

    for ref_tweet in tweet.get("referenced_tweets", []):
      if isinstance(ref_tweet, str):
        continue
      tweet_type = ref_tweet["type"]
      actual = ref_tweet["tweet"]
      if actual is None:
        referenced = None
        continue
      ref_author = actual.get("user", {}).get("username")
      ref_urls = self._extract_urls_from_tweet(actual)
      referenced = {
        "text": actual.get("note_tweet", actual).get("text"),
        "user": f"@{ref_author}" if ref_author else None,
        "date": actual["created_at"]
      }
      if ref_urls:
        referenced["urls"] = ref_urls

    urls = self._extract_urls_from_tweet(tweet)

    filtered = {
      "text": text,
      "user": f"@{author_tag}" if author_tag else None,
      "date": tweet["created_at"],
      "id": tweet["id"],
      "type": tweet_type,
    }

    if metrics := tweet.get("public_metrics"):
      filtered["metrics"] = {
        k: v for k, v in {
          "likes": metrics.get("like_count"),
          "retweets": metrics.get("retweet_count"),
          "replies": metrics.get("reply_count"),
          "quotes": metrics.get("quote_count"),
          "views": metrics.get("impression_count"),
        }.items() if v
      }

    if tweet_type != "original":
      filtered["referenced"] = referenced

    if urls:
      filtered["urls"] = urls

    if "retweeted_by" in tweet:
      filtered["retweeted_by"] = tweet["retweeted_by"]

    if "thread_info" in tweet:
      thread_info = tweet["thread_info"].copy()
      if "thread_tweets" in thread_info:
        filtered_thread = []
        for t in thread_info["thread_tweets"]:
          thread_urls = self._extract_urls_from_tweet(t)
          obj = {
            "text": t.get("note_tweet", t).get("text"),
            "user": f"@{t.get('user', {}).get('username')}" if t.get('user', {}).get('username') else None,
            "date": t["created_at"],
            "id": t["id"]
          }
          if thread_urls:
            obj["urls"] = thread_urls
          filtered_thread.append(obj)
        thread_info["thread_tweets"] = filtered_thread
      filtered["thread_info"] = thread_info

    return filtered
