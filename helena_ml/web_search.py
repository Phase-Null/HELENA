"""
HELENA Web Search
 
Provides web search capability using DuckDuckGo HTML search
(no API key required) and Wikipedia as a fallback for factual queries.
 
Designed to be called from _detect_tool_intent() in chat_engine.py.
All search is done over HTTPS. Results are summarised before being
passed to the LLM to avoid context overflow.
"""
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Optional
 
 
class WebSearch:
    """
    Web search using DuckDuckGo HTML search and Wikipedia summary API.
 
    DuckDuckGo: No API key, no rate limit for reasonable use.
    Wikipedia:  No API key, excellent for factual/definition queries.
    """
 
    DDG_URL = "https://html.duckduckgo.com/html/"
    WIKI_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    TIMEOUT = 8
 
    def __init__(self):
        self.available = self._check_connectivity()
 
    def _check_connectivity(self) -> bool:
        try:
            urllib.request.urlopen(
                "https://www.google.com",
                timeout=3
            )
            return True
        except Exception:
            return False
 
    def search(self, query: str, max_results: int = 5) -> Dict:
        """
        Search DuckDuckGo for query using HTML endpoint.
        Returns dict with 'results', 'ok', 'query'.
        """
        if not self.available:
            return {"ok": False, "error": "No internet connection", "results": []}
 
        try:
            params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
            url = f"{self.DDG_URL}?{params}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
 
            results = self._parse_ddg_html(html, max_results)
 
            return {
                "ok": True,
                "query": query,
                "results": results,
                "count": len(results)
            }
 
        except Exception as e:
            return {"ok": False, "error": str(e), "results": []}
 
    def _parse_ddg_html(self, html: str, max_results: int) -> List[Dict]:
        """Parse DDG HTML results page into structured results."""
        results = []
 
        # DDG HTML results are in <div class="result"> blocks
        # Extract result titles, snippets, and URLs
        # Title pattern
        title_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        # Snippet pattern
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span)>',
            re.DOTALL
        )
 
        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)
 
        for i, (url, title) in enumerate(titles[:max_results]):
            snippet = snippets[i] if i < len(snippets) else ""
            # Clean HTML tags and whitespace
            title = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            snippet = re.sub(r"\s+", " ", snippet)
            # Decode DDG redirect URLs
            if "uddg=" in url:
                try:
                    url = urllib.parse.unquote(
                        re.search(r"uddg=([^&]+)", url).group(1)
                    )
                except Exception:
                    pass
            if title and snippet:
                results.append({
                    "title": title,
                    "snippet": snippet[:400],
                    "url": url,
                    "type": "result"
                })
 
        return results
 
    def wikipedia(self, topic: str) -> Dict:
        """
        Get a Wikipedia summary for a topic.
        Good for factual questions about people, places, concepts.
        """
        if not self.available:
            return {"ok": False, "error": "No internet connection"}
 
        try:
            encoded = urllib.parse.quote(topic.replace(" ", "_"))
            url = f"{self.WIKI_URL}{encoded}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "HELENA-AI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
 
            return {
                "ok": True,
                "title": data.get("title", topic),
                "summary": data.get("extract", "")[:800],
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", "")
            }
 
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"ok": False, "error": f"No Wikipedia article found for '{topic}'"}
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
 
    def format_results(self, search_result: Dict) -> str:
        """Format search results into a readable string for HELENA's response."""
        if not search_result.get("ok"):
            return f"Search failed: {search_result.get('error', 'unknown error')}"
 
        results = search_result.get("results", [])
        if not results:
            return f"No results found for '{search_result.get('query', '')}'"
 
        lines = []
        for r in results:
            if r.get("title") and r.get("snippet"):
                lines.append(f"**{r['title']}**\n{r['snippet']}")
                if r.get("url"):
                    lines.append(f"Source: {r['url']}")
 
        return "\n\n".join(lines)
