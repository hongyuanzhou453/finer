"""F1/F2 Enrichment API — manage content enrichment and linking."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime

from finer.config import load_feishu_config
from finer.enrichment import (
    TopicSplitter,
    EntityExtractor,
    ContentLinker,
    get_content_linker,
    Topic,
    EntityExtraction,
)
from finer.paths import REPO_ROOT, DATA_ROOT

router = APIRouter()
L1_DIR = DATA_ROOT / "L1_enrichment"


class EnrichmentRequest(BaseModel):
    content_id: str
    content: str
    force_refresh: bool = False


class TopicResponse(BaseModel):
    title: str
    tickers: List[str]
    companies: List[str]
    summary: str
    time_range: Dict[str, str]


class EntityResponse(BaseModel):
    tickers: List[str]
    companies: List[str]
    people: List[str]
    events: List[str]
    concepts: List[str]
    related_content: List[str]


class TickerGroup(BaseModel):
    ticker: str
    companies: List[str]
    content_count: int
    content_ids: List[str]


@router.post("/split")
async def split_content(req: EnrichmentRequest):
    """Split content into topics."""
    splitter = TopicSplitter()
    topics = splitter.split(req.content)

    return {
        "content_id": req.content_id,
        "topics_count": len(topics),
        "topics": [
            {
                "title": t.title,
                "tickers": t.tickers,
                "companies": t.companies,
                "summary": t.summary,
                "time_range": t.time_range,
            }
            for t in topics
        ]
    }


@router.post("/extract")
async def extract_entities(req: EnrichmentRequest):
    """Extract entities from content."""
    extractor = EntityExtractor()
    entities = extractor.extract(req.content)

    # Index the content
    linker = get_content_linker(REPO_ROOT)
    linker.index_content(req.content_id, entities)

    # Find related content
    related = linker.find_related(req.content_id)

    # Save index
    L1_DIR.mkdir(parents=True, exist_ok=True)
    linker.save_index(L1_DIR / "content_index.json")

    return {
        "content_id": req.content_id,
        "entities": {
            "tickers": entities.tickers,
            "companies": entities.companies,
            "people": entities.people,
            "events": entities.events,
            "concepts": entities.concepts,
            "metrics": entities.metrics,
        },
        "related_content": related,
    }


@router.get("/by-ticker/{ticker}")
async def get_by_ticker(ticker: str):
    """Get all content related to a ticker."""
    linker = get_content_linker(REPO_ROOT)
    content_ids = linker.get_by_ticker(ticker)

    return {
        "ticker": ticker,
        "content_count": len(content_ids),
        "content_ids": content_ids,
    }


@router.get("/by-company/{company}")
async def get_by_company(company: str):
    """Get all content related to a company."""
    linker = get_content_linker(REPO_ROOT)
    content_ids = linker.get_by_company(company)

    return {
        "company": company,
        "content_count": len(content_ids),
        "content_ids": content_ids,
    }


@router.get("/tickers")
async def list_tickers():
    """List all indexed tickers with their content counts."""
    linker = get_content_linker(REPO_ROOT)

    tickers = []
    seen_tickers = set()

    for entity, content_ids in linker.index.items():
        # Check if it looks like a ticker (uppercase, short)
        if entity.isupper() and len(entity) <= 6 and entity not in seen_tickers:
            seen_tickers.add(entity)
            tickers.append(TickerGroup(
                ticker=entity,
                companies=[],
                content_count=len(content_ids),
                content_ids=content_ids[:10],  # Limit for display
            ))

    return {
        "tickers": [t.model_dump() for t in sorted(tickers, key=lambda x: -x.content_count)],
        "total_tickers": len(tickers),
    }


@router.get("/companies")
async def list_companies():
    """List all indexed companies with their content counts."""
    linker = get_content_linker(REPO_ROOT)

    companies = []
    seen = set()

    for entity, content_ids in linker.index.items():
        # Check if it looks like a company name (Chinese characters or long names)
        if (any('\u4e00' <= c <= '\u9fff' for c in entity) or len(entity) > 6) and entity not in seen:
            seen.add(entity)
            companies.append({
                "company": entity,
                "content_count": len(content_ids),
                "content_ids": content_ids[:10],
            })

    return {
        "companies": sorted(companies, key=lambda x: -x["content_count"]),
        "total_companies": len(companies),
    }


@router.post("/rebuild-index")
async def rebuild_index():
    """Rebuild the content index from all manifests."""
    from finer.api.routes.files_utils import get_manifests_index

    linker = ContentLinker()
    extractor = EntityExtractor()

    manifests_index = get_manifests_index()
    processed = 0

    for content_id, (manifest, path) in manifests_index["by_content_id"].items():
        source_path = manifest.get("raw_path") or manifest.get("source_path")
        if source_path:
            source_file = Path(source_path)
            if source_file.exists() and source_file.suffix in [".md", ".txt"]:
                try:
                    content = source_file.read_text(encoding="utf-8")
                    entities = extractor.extract(content[:2000])  # Limit for speed
                    linker.index_content(content_id, entities)
                    processed += 1
                except Exception as e:
                    pass

    # Save the index
    L1_DIR.mkdir(parents=True, exist_ok=True)
    linker.save_index(L1_DIR / "content_index.json")

    return {
        "status": "ok",
        "processed": processed,
        "total_manifests": len(manifests_index["by_content_id"]),
    }


@router.get("/status")
async def get_enrichment_status():
    """Get F1/F2 enrichment status."""
    index_path = L1_DIR / "content_index.json"

    status = {
        "l1_dir_exists": L1_DIR.exists(),
        "index_exists": index_path.exists(),
        "by_ticker_dir": (L1_DIR / "by_ticker").exists(),
        "by_event_dir": (L1_DIR / "by_event").exists(),
        "by_topic_dir": (L1_DIR / "by_topic").exists(),
    }

    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            status["indexed_entities"] = len(data.get("index", {}))
            status["indexed_content"] = len(data.get("content_entities", {}))
        except:
            status["indexed_entities"] = 0
            status["indexed_content"] = 0

    return status
