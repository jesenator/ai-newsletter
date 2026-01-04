"""Web tools for the newsletter agent."""

import asyncio
import json
import os
from agents import function_tool
from openai import AsyncOpenAI


@function_tool
async def search_web(query: str, num_results: int = 5) -> str:
  """Search Google (via Serper) and return a JSON string of results."""
  import aiohttp
  num_results = max(1, min(num_results, 20))
  print(f"\n[search_web] Searching '{query}' (top {num_results})... ", end="", flush=True)
  async with aiohttp.ClientSession() as session:
    headers = {
      'X-API-KEY': os.getenv("SERPER_API_KEY"),
      'Content-Type': 'application/json'
    }
    payload = {"q": query, "num": num_results}
    async with session.post('https://google.serper.dev/search', json=payload, headers=headers) as response:
      output = await response.json()
  print("done", end="", flush=True)
  return json.dumps(output.get('organic', []))


@function_tool
async def scrape_webpage(url: str) -> str:
  """Return the scraped text content of a webpage (via Serper)."""
  import aiohttp
  print(f"\n[scrape_webpage] Fetching {url}... ", end="", flush=True)
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
      print("done", end="", flush=True)
      return content.get('markdown', content.get('message', json.dumps(content)))
    except asyncio.TimeoutError:
      print("timeout", end="", flush=True)
      return f"Error: Timeout after 8 seconds while scraping {url}"


@function_tool
async def ask_perplexity(query: str) -> str:
  """Ask Perplexity AI for current information and research."""
  print(f"\n[ask_perplexity] Asking: '{query[:100]}{'...' if len(query) > 100 else ''}'... ", end="", flush=True)
  client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
  )
  response = await client.chat.completions.create(
    model="perplexity/sonar-pro",
    messages=[{"role": "user", "content": query + " Be concise without losing detail."}]
  )
  print("done", end="", flush=True)
  return response.choices[0].message.content


ALL_TOOLS = [search_web, scrape_webpage, ask_perplexity]

