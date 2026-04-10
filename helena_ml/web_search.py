"""
HELENA Web Search

Provides web search capability using DuckDuckGo (no API key required)
and Wikipedia as a fallback for factual queries.

Designed to be called from _detect_tool_intent() in chat_engine.py.
All search is done over HTTPS. Results are summarised before being
passed to the LLM to avoid context overflow.
"""
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Optional


class WebSearch:
    """
    Offline-friendly web search using DuckDuckGo Instant Answer API
    and Wikipedia summary API.

    DuckDuckGo: No API key, no rate limit for reasonable use.
    Wikipedia:  No API key, excellent for factual/definition queries.
    """

    DDG_URL = "https://api.duckduckgo.com/"
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
        Search DuckDuckGo for query.
        Returns dict with 'results', 'abstract', 'answer'.
        """
        if not self.available:
            return {"ok": False, "error": "No internet connection", "results": []}

        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            url = f"{self.DDG_URL}?{params}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "HELENA-AI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []

            # Instant answer
            if data.get("Answer"):
                results.append({
                    "title": "Direct Answer",
                    "snippet": data["Answer"],
                    "url": "",
                    "type": "answer"
                })

            # Abstract (Wikipedia-sourced summary)
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", "Summary"),
                    "snippet": data["AbstractText"][:500],
                    "url": data.get("AbstractURL", ""),
                    "type": "abstract"
                })

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        "snippet": topic["Text"][:300],
                        "url": topic.get("FirstURL", ""),
                        "type": "related"
                    })

            return {
                "ok": True,
                "query": query,
                "results": results[:max_results],
                "count": len(results)
            }

        except Exception as e:
            return {"ok": False, "error": str(e), "results": []}

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
            if r["type"] == "answer":
                lines.append(f"**Direct answer:** {r['snippet']}")
            elif r["type"] == "abstract":
                lines.append(f"{r['snippet']}")
                if r["url"]:
                    lines.append(f"Source: {r['url']}")
            else:
                if r["title"]:
                    lines.append(f"**{r['title']}:** {r['snippet']}")

        return "\n\n".join(lines)
