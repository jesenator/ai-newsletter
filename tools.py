"""Web tools for the newsletter agent."""

import asyncio
import json
import os
from agents import function_tool
from openai import AsyncOpenAI

from logger import log_tool_call, log_error


@function_tool
async def search_web(query: str, num_results: int = 5) -> str:
  """Search Google (via Serper) and return a JSON string of results."""
  import aiohttp
  num_results = max(1, min(num_results, 20))
  print(f"\n[search_web] Searching '{query}' (top {num_results})... ", end="", flush=True)
  log_tool_call("search_web", f"query={query}, num_results={num_results}")
  async with aiohttp.ClientSession() as session:
    headers = {
      'X-API-KEY': os.getenv("SERPER_API_KEY"),
      'Content-Type': 'application/json'
    }
    payload = {"q": query, "num": num_results}
    async with session.post('https://google.serper.dev/search', json=payload, headers=headers) as response:
      output = await response.json()
  result = json.dumps(output.get('organic', []))
  print("done", end="", flush=True)
  log_tool_call("search_web", f"query={query}", result)
  return result


MAX_SCRAPE_CHARS = 8000

@function_tool
async def scrape_webpage(url: str) -> str:
  """Return the scraped text content of a webpage (via Serper). Truncated to ~8000 chars."""
  import aiohttp
  print(f"\n[scrape_webpage] Fetching {url}... ", end="", flush=True)
  log_tool_call("scrape_webpage", f"url={url}")
  timeout = aiohttp.ClientTimeout(total=8)
  async with aiohttp.ClientSession(timeout=timeout) as session:
    headers = {
      'X-API-KEY': os.getenv("SERPER_API_KEY"),
      'Content-Type': 'application/json'
    }
    payload = {"url": url, "includeMarkdown": True}
    try:
      async with session.post('https://scrape.serper.dev', json=payload, headers=headers) as response:
        content = await response.json()
      result = content.get('markdown', content.get('message', json.dumps(content)))
      if len(result) > MAX_SCRAPE_CHARS:
        result = result[:MAX_SCRAPE_CHARS] + "\n\n[Content truncated...]"
      print("done", end="", flush=True)
      log_tool_call("scrape_webpage", f"url={url}", result)
      return result
    except asyncio.TimeoutError:
      err = f"Error: Timeout after 8 seconds while scraping {url}"
      print("timeout", end="", flush=True)
      log_error(err)
      return err


@function_tool
async def ask_perplexity(query: str) -> str:
  """Ask Perplexity AI for current information and research."""
  print(f"\n[ask_perplexity] Asking: '{query[:100]}{'...' if len(query) > 100 else ''}'... ", end="", flush=True)
  log_tool_call("ask_perplexity", f"query={query[:200]}{'...' if len(query) > 200 else ''}")
  client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
  )
  try:
    response = await client.chat.completions.create(
      model="perplexity/sonar-pro",
      messages=[{"role": "user", "content": query + " Be concise without losing detail."}]
    )
    result = response.choices[0].message.content
    print("done", end="", flush=True)
    log_tool_call("ask_perplexity", f"query={query[:100]}", result)
    return result
  except Exception as e:
    log_error(f"ask_perplexity failed for query: {query[:100]}", e)
    raise
  finally:
    await client.close()


ALL_TOOLS = [search_web, scrape_webpage, ask_perplexity]

