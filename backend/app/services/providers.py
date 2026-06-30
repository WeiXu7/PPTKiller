from __future__ import annotations

from dataclasses import dataclass
import re
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
    provider: str = "Crossref"


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
                    provider="Crossref",
                )
            )
        return citations


class SemanticScholarLiteratureProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    async def search(self, query: str, limit: int = 8) -> list[Citation]:
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        fields = "title,authors,year,venue,url,externalIds,openAccessPdf"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                headers=headers,
                params={"query": query, "limit": limit, "fields": fields},
            )
            response.raise_for_status()
        citations = []
        for item in response.json().get("data", []):
            external_ids = item.get("externalIds") or {}
            doi = external_ids.get("DOI")
            access_pdf = item.get("openAccessPdf") or {}
            citations.append(
                Citation(
                    title=item.get("title") or "Untitled",
                    authors=[author.get("name", "") for author in item.get("authors", []) if author.get("name")],
                    year=item.get("year"),
                    venue=item.get("venue") or "",
                    url=access_pdf.get("url") or item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
                    doi=doi,
                    verified=bool(doi),
                    provider="Semantic Scholar",
                )
            )
        return citations


class OpenAlexLiteratureProvider:
    async def search(self, query: str, limit: int = 8) -> list[Citation]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.openalex.org/works",
                params={"search": query, "per-page": limit, "sort": "relevance_score:desc"},
            )
            response.raise_for_status()
        citations = []
        for item in response.json().get("results", []):
            doi_url = item.get("doi") or ""
            doi = doi_url.removeprefix("https://doi.org/") or None
            host_venue = item.get("host_venue") or {}
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            citations.append(
                Citation(
                    title=item.get("display_name") or "Untitled",
                    authors=[
                        authorship.get("author", {}).get("display_name", "")
                        for authorship in item.get("authorships", [])
                        if authorship.get("author", {}).get("display_name")
                    ],
                    year=item.get("publication_year"),
                    venue=source.get("display_name") or host_venue.get("display_name") or "",
                    url=doi_url or item.get("id") or "",
                    doi=doi,
                    verified=bool(doi),
                    provider="OpenAlex",
                )
            )
        return citations


class PubMedLiteratureProvider:
    async def search(self, query: str, limit: int = 8) -> list[Citation]:
        async with httpx.AsyncClient(timeout=20) as client:
            search_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed", "term": query, "retmode": "json", "retmax": limit},
            )
            search_response.raise_for_status()
            ids = search_response.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            summary_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            )
            summary_response.raise_for_status()
        result = summary_response.json().get("result", {})
        citations = []
        for pubmed_id in result.get("uids", []):
            item = result.get(pubmed_id, {})
            doi = _pubmed_doi(item.get("articleids", []))
            citations.append(
                Citation(
                    title=item.get("title") or "Untitled",
                    authors=[author.get("name", "") for author in item.get("authors", []) if author.get("name")],
                    year=_year_from_pubdate(item.get("pubdate", "")),
                    venue=item.get("fulljournalname") or item.get("source") or "",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                    doi=doi,
                    verified=bool(doi),
                    provider="PubMed",
                )
            )
        return citations


def citation_identity(citation: Citation | dict) -> str:
    doi = (citation.doi if isinstance(citation, Citation) else citation.get("doi")) or ""
    if doi:
        return f"doi:{doi.lower().strip()}"
    title = citation.title if isinstance(citation, Citation) else citation.get("title", "")
    normalized_title = re.sub(r"\W+", " ", title.lower()).strip()
    return f"title:{normalized_title}"


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen = set()
    unique = []
    for citation in citations:
        key = citation_identity(citation)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def _pubmed_doi(article_ids: list[dict]) -> str | None:
    for article_id in article_ids:
        if article_id.get("idtype") == "doi" and article_id.get("value"):
            return article_id["value"]
    return None


def _year_from_pubdate(pubdate: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", pubdate or "")
    return int(match.group(0)) if match else None


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
        "literature": {
            "configured": True,
            "provider": "Crossref + Semantic Scholar + OpenAlex + PubMed",
            "semantic_scholar_key": bool(settings.semantic_scholar_api_key),
        },
        "images": {
            "configured": bool(settings.unsplash_access_key or settings.pexels_api_key),
            "provider": "Unsplash" if settings.unsplash_access_key else "Pexels" if settings.pexels_api_key else "未配置",
        },
        "redis": {"configured": bool(settings.redis_url), "provider": "Redis"},
    }
