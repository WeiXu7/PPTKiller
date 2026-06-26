from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import Settings


@dataclass
class Citation:
    title: str
    authors: list[str]
    year: int | None
    venue: str
    url: str
    doi: str | None = None
    verified: bool = False


class ResearchProvider(Protocol):
    async def search(self, query: str, limit: int = 8) -> list[dict]: ...


class LiteratureProvider(Protocol):
    async def search(self, query: str, limit: int = 8) -> list[Citation]: ...


class ImageProvider(Protocol):
    async def search(self, query: str, limit: int = 8) -> list[dict]: ...


class CrossrefLiteratureProvider:
    async def search(self, query: str, limit: int = 8) -> list[Citation]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.crossref.org/works",
                params={"query": query, "rows": limit, "select": "DOI,title,author,published,container-title,URL"},
            )
            response.raise_for_status()
        citations = []
        for item in response.json()["message"]["items"]:
            date_parts = item.get("published", {}).get("date-parts", [[]])
            authors = [
                " ".join(part for part in [author.get("given"), author.get("family")] if part)
                for author in item.get("author", [])
            ]
            citations.append(
                Citation(
                    title=(item.get("title") or ["Untitled"])[0],
                    authors=authors,
                    year=date_parts[0][0] if date_parts and date_parts[0] else None,
                    venue=(item.get("container-title") or [""])[0],
                    url=item.get("URL", ""),
                    doi=item.get("DOI"),
                    verified=bool(item.get("DOI")),
                )
            )
        return citations


class TavilyResearchProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, limit: int = 8) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": limit, "search_depth": "advanced"},
            )
            response.raise_for_status()
        return response.json().get("results", [])


class UnsplashImageProvider:
    def __init__(self, access_key: str):
        self.access_key = access_key

    async def search(self, query: str, limit: int = 8) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {self.access_key}"},
                params={"query": query, "per_page": limit, "orientation": "landscape"},
            )
            response.raise_for_status()
        return [
            {
                "id": item["id"],
                "url": item["urls"]["regular"],
                "thumb": item["urls"]["small"],
                "description": item.get("description") or item.get("alt_description"),
                "author": item["user"]["name"],
                "source_url": item["links"]["html"],
            }
            for item in response.json().get("results", [])
        ]


def provider_status(settings: Settings) -> dict[str, dict[str, str | bool]]:
    web_provider = "Tavily" if settings.tavily_api_key else "SerpAPI" if settings.serpapi_api_key else "未配置"
    return {
        "model": {
            "configured": bool(settings.deepseek_api_key),
            "provider": "DeepSeek",
            "model": settings.deepseek_model,
            "thinking": settings.deepseek_thinking,
        },
        "web_search": {
            "configured": bool(settings.serpapi_api_key or settings.tavily_api_key),
            "provider": web_provider,
        },
        "literature": {"configured": True, "provider": "Crossref", "optional": "Semantic Scholar"},
        "images": {
            "configured": bool(settings.unsplash_access_key or settings.pexels_api_key),
            "provider": "Unsplash" if settings.unsplash_access_key else "Pexels" if settings.pexels_api_key else "未配置",
        },
        "redis": {"configured": bool(settings.redis_url), "provider": "Redis"},
    }
