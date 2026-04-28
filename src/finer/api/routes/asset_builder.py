"""Asset construction — builds AssetFile lists for each workflow stage."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import re
import time
import logging
from finer.schemas.contract import AssetFile, ReviewPayload, ReviewActionPayload
from datetime import datetime

from finer.api.routes.files_utils import (
    DATA_ROOT,
    STAGE_BADGE_BY_WORKFLOW,
    _assets_cache,
    _CACHE_TTL_SECONDS,
    get_manifests_index,
    collect_files_from_directories,
    read_json_file,
    read_preview,
    build_match_tokens,
    first_matching_path,
    format_file_size,
    format_display_name,
    file_type_for,
    extract_source_info,
    extract_file_timestamp,
    build_display_info,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Review payload builders
# ---------------------------------------------------------------------------

def build_review_payload_from_candidate(candidate_path: Optional[Path]) -> Optional[ReviewPayload]:
    if not candidate_path or not candidate_path.exists():
        return None

    payload = read_json_file(candidate_path)
    if not payload:
        return None

    first_event = payload[0] if isinstance(payload, list) else payload
    if not isinstance(first_event, dict):
        return None

    direction = first_event.get("direction", "watchlist")
    if direction not in ["bullish", "bearish", "neutral", "watchlist", "risk_warning"]:
        direction = "watchlist"

    chain = first_event.get("action_chain", [])
    if not isinstance(chain, list):
        chain = []

    action_chain = []
    for i, action in enumerate(chain):
        item = action if isinstance(action, dict) else {}
        conf = item.get("confidence", 0.8)
        action_chain.append(
            ReviewActionPayload(
                id=f"action-{i + 1}",
                actionType=str(item.get("action_type", "watch")),
                instrumentType=str(item.get("instrument_type", "unspecified")),
                triggerCondition=str(item.get("trigger_condition", "")),
                targetPriceLow=str(item.get("target_price_low", "")),
                targetPriceHigh=str(item.get("target_price_high", "")),
                confidence=float(conf) if conf is not None else 0.8,
                status="watch" if direction == "watchlist" else "active"
            )
        )

    if not action_chain:
        action_chain.append(
            ReviewActionPayload(
                id="action-1", actionType="watch", instrumentType="unspecified",
                triggerCondition="", targetPriceLow="", targetPriceHigh="",
                confidence=0.72, status="watch"
            )
        )

    return ReviewPayload(
        ticker=str(first_event.get("ticker", "待确认标的")),
        direction=direction,
        timeHorizon=str(first_event.get("time_horizon", "weekly")),
        rationale=str(first_event.get("rationale", "")),
        evidenceText=str(first_event.get("evidence_text", "")),
        confidence=action_chain[0].confidence if action_chain else 0.84,
        tags=[str(first_event.get("ticker", "")), direction],
        ambiguityNotes=[
            "确认自然语言观点是否真的对应当前 action chain。",
            "确认字段是否足以支持后续 proxy 映射与回测。"
        ],
        actionChain=action_chain
    )


def build_fallback_review_payload(summary: str, tags: List[str]) -> ReviewPayload:
    return ReviewPayload(
        ticker="待确认标的",
        direction="watchlist",
        timeHorizon="weekly",
        rationale="",
        evidenceText=summary or "当前还没有候选事件证据，请先补充抽取结果或解析证据。",
        confidence=0.56,
        tags=tags,
        ambiguityNotes=[
            "当前对象缺少结构化候选事件，需要人工补全字段。",
            "建议先确认标的、方向和 trigger condition 再进入回测。"
        ],
        actionChain=[
            ReviewActionPayload(
                id="action-1", actionType="watch", instrumentType="unspecified",
                triggerCondition="", targetPriceLow="", targetPriceHigh="",
                confidence=0.56, status="draft"
            )
        ]
    )


# ---------------------------------------------------------------------------
# Single manifest → AssetFile
# ---------------------------------------------------------------------------

def build_manifest_asset(
    manifest: Dict, manifest_path: Path, workflow_stage: str,
    evidence_paths: List[Path], candidate_paths: List[Path], approved_paths: List[Path]
) -> AssetFile:
    content_id = manifest.get("content_id", "unknown")
    title = manifest.get("title")
    source_path = manifest.get("source_path")

    tokens = build_match_tokens(content_id, title, source_path)
    evidence_path = first_matching_path(evidence_paths, tokens)
    candidate_event_path = first_matching_path(candidate_paths, tokens)
    approved_event_path = first_matching_path(approved_paths, tokens)

    metadata = manifest.get("metadata", {})
    summary = read_preview(evidence_path) or str(metadata.get("context_text", "")) or \
              f"Canonical content record for {manifest.get('creator_name', 'unknown creator')}."

    if workflow_stage == "review":
        status = "approved" if approved_event_path else "needs review"
    elif workflow_stage == "extraction":
        status = "candidate ready" if candidate_event_path else "awaiting extraction"
    elif workflow_stage == "parsing":
        status = "evidence ready" if evidence_path else "awaiting parse"
    else:
        status = "canonical"

    creator_name = manifest.get("creator_name", "unknown")
    content_type = manifest.get("content_type", "unknown")

    tags = [t for t in [content_type, creator_name] if t]
    review_payload = build_review_payload_from_candidate(candidate_event_path)
    if (workflow_stage in ["extraction", "review"]) and not review_payload:
        review_payload = build_fallback_review_payload(summary, tags)

    size_str = format_file_size(Path(source_path)) if source_path and Path(source_path).exists() else "--"
    pub_date = str(manifest.get("published_at", ""))[:10]
    if not pub_date:
        pub_date = datetime.utcnow().isoformat()[:10]

    source_type, group_id, group_name = extract_source_info(manifest, source_path)
    file_timestamp = extract_file_timestamp(manifest, Path(source_path) if source_path else None)

    content_type = manifest.get("content_type", "unknown")
    display_name = format_display_name(title or content_id, content_type)

    # Build semantic display fields
    extension = file_type_for(source_path or title or content_id)
    content_text = read_preview(evidence_path) or str(metadata.get("context_text", ""))
    display_info = build_display_info(
        file_name=title or content_id,
        extension=extension,
        source_group_name=group_name,
        content_text=content_text,
    )

    return AssetFile(
        id=content_id,
        name=display_name,
        size=size_str,
        date=pub_date,
        type=extension,
        status=status,
        workflowStage=workflow_stage,
        stageBadge=STAGE_BADGE_BY_WORKFLOW.get(workflow_stage, "F1"),
        creatorName=creator_name,
        sourcePlatform=manifest.get("source_platform", "unknown"),
        contentType=content_type,
        contentId=content_id,
        sourcePath=source_path or "",
        manifestPath=str(manifest_path),
        evidencePath=str(evidence_path) if evidence_path else None,
        candidateEventPath=str(candidate_event_path) if candidate_event_path else None,
        approvedEventPath=str(approved_event_path) if approved_event_path else None,
        summary=summary,
        tags=tags,
        reviewPayload=review_payload,
        sourceType=source_type,
        sourceGroupId=group_id,
        sourceGroupName=group_name,
        fileTimestamp=file_timestamp,
        fileType=display_info["fileType"],
        sourceName=display_info["sourceName"],
        semanticTitle=display_info["semanticTitle"],
    )


# ---------------------------------------------------------------------------
# Workflow assets — public entry point
# ---------------------------------------------------------------------------

def build_workflow_assets(workflow_stage: str, use_cache: bool = True) -> List[AssetFile]:
    """Build asset list for a workflow stage with optional TTL caching."""
    cache_key = f"assets:{workflow_stage}"
    now = time.time()

    if use_cache and cache_key in _assets_cache:
        cached_assets, cached_at = _assets_cache[cache_key]
        if now - cached_at < _CACHE_TTL_SECONDS:
            logger.debug("Returning cached assets for %s (age: %.1fs)", workflow_stage, now - cached_at)
            return cached_assets

    assets = _build_workflow_assets_uncached(workflow_stage)

    if use_cache:
        _assets_cache[cache_key] = (assets, now)
        logger.debug("Cached %d assets for %s", len(assets), workflow_stage)

    return assets


# ---------------------------------------------------------------------------
# Workflow assets — uncached builder (the big one)
# ---------------------------------------------------------------------------

def _build_workflow_assets_uncached(workflow_stage: str) -> List[AssetFile]:
    index = get_manifests_index()
    manifests_by_content_id = index["by_content_id"]
    manifests_by_source_name = index["by_source_name"]
    manifests_data = list(manifests_by_content_id.values())

    raw_paths = []
    for p in collect_files_from_directories([DATA_ROOT / "raw", DATA_ROOT / "L0_ingest"]):
        if not p.name.endswith(".json"):
            raw_paths.append(p)

    evidence_paths = collect_files_from_directories([
        DATA_ROOT / "processed" / "documents", DATA_ROOT / "processed" / "transcripts",
        DATA_ROOT / "L3_aligned" / "documents", DATA_ROOT / "L3_aligned" / "transcripts", DATA_ROOT / "L3_aligned" / "blocks_md"
    ])

    candidate_paths = collect_files_from_directories([
        DATA_ROOT / "processed" / "review_store",
        DATA_ROOT / "processed" / "candidate_events",
        DATA_ROOT / "L4_parsed" / "candidate_events",
        DATA_ROOT / "L3_aligned" / "candidate_events",
    ])

    candidate_paths.sort(key=lambda p: 0 if "review_store" in str(p) else 1)

    approved_paths = collect_files_from_directories([
        DATA_ROOT / "processed" / "approved_events",
        DATA_ROOT / "L3_aligned" / "approved_events",
        DATA_ROOT / "L6_annotated",
    ])

    backtest_paths = collect_files_from_directories([
        DATA_ROOT / "backtests",
        DATA_ROOT / "L8_metrics",
    ])

    assets: List[AssetFile] = []

    if workflow_stage == "intake":
        for rp in raw_paths:
            source_name = rp.name
            manifest_tuple = manifests_by_source_name.get(source_name)
            manifest = manifest_tuple[0] if manifest_tuple else None

            parts = rp.relative_to(DATA_ROOT).parts
            creator_name = manifest.get("creator_name") if manifest else (parts[1] if len(parts) > 1 else "_inbox")
            content_type = manifest.get("content_type") if manifest else (parts[2] if len(parts) > 2 else "unclassified")

            summary_txt = "Raw asset waiting for classification, registration, or downstream parsing."
            if manifest and manifest.get("metadata", {}).get("context_text"):
                summary_txt = manifest["metadata"]["context_text"]

            source_type, group_id, group_name = extract_source_info(manifest, str(rp))
            file_timestamp = extract_file_timestamp(manifest, rp)

            file_id = manifest.get("content_id") if manifest else f"raw:{rp.relative_to(DATA_ROOT)}"
            if any(a.id == file_id for a in assets):
                import hashlib
                path_hash = hashlib.md5(str(rp).encode()).hexdigest()[:8]
                file_id = f"{file_id}_{path_hash}"

            display_name = format_display_name(source_name, content_type)

            # Build semantic display fields for intake
            extension = file_type_for(str(rp))
            display_info = build_display_info(
                file_name=source_name,
                extension=extension,
                source_group_name=group_name,
                content_text=summary_txt if len(summary_txt) > 50 else None,
            )

            assets.append(AssetFile(
                id=file_id,
                name=display_name,
                size=format_file_size(rp),
                date=datetime.fromtimestamp(rp.stat().st_mtime).isoformat()[:10],
                type=extension,
                status="registered" if manifest else "unclassified",
                workflowStage="intake",
                stageBadge=STAGE_BADGE_BY_WORKFLOW["intake"],
                creatorName=creator_name,
                sourcePlatform=manifest.get("source_platform", "manual_or_feishu") if manifest else "manual_or_feishu",
                contentType=content_type,
                contentId=manifest.get("content_id") if manifest else source_name,
                sourcePath=str(rp),
                manifestPath=str(manifest_tuple[1]) if manifest_tuple else None,
                summary=summary_txt,
                tags=[creator_name, content_type],
                sourceType=source_type,
                sourceGroupId=group_id,
                sourceGroupName=group_name,
                fileTimestamp=file_timestamp,
                fileType=display_info["fileType"],
                sourceName=display_info["sourceName"],
                semanticTitle=display_info["semanticTitle"],
            ))

    elif workflow_stage == "enrichment":
        import json
        enrichment_index_path = DATA_ROOT / "L1_enrichment" / "content_index.json"
        topic_dir = DATA_ROOT / "L1_enrichment" / "by_topic"

        enrichment_index = {}
        if enrichment_index_path.exists():
            try:
                enrichment_index = json.loads(enrichment_index_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        for entity, content_ids in enrichment_index.get("index", {}).items():
            if len(content_ids) > 0:
                assets.append(AssetFile(
                    id=f"enrichment:{entity}",
                    name=f"{entity} ({len(content_ids)} 内容)",
                    size=f"{len(content_ids)} files",
                    date=datetime.now().isoformat()[:10],
                    type="folder",
                    status="indexed",
                    workflowStage="enrichment",
                    stageBadge=STAGE_BADGE_BY_WORKFLOW["enrichment"],
                    creatorName="enrichment",
                    sourcePlatform="pipeline",
                    contentType="ticker_group" if entity.isupper() else "company_group",
                    contentId=f"enrichment:{entity}",
                    sourcePath=None,
                    manifestPath=None,
                    summary=f"按 {entity} 归类的内容集合，共 {len(content_ids)} 条",
                    tags=["enrichment", entity],
                    sourceType="local",
                    sourceGroupId=None,
                    sourceGroupName=None,
                    fileTimestamp=datetime.now().isoformat(),
                    fileType="文件夹",
                    sourceName=entity,
                    semanticTitle="",
                ))

        if topic_dir.exists():
            for topic_file in topic_dir.glob("*.md"):
                assets.append(AssetFile(
                    id=f"topic:{topic_file.stem}",
                    name=topic_file.stem,
                    size=format_file_size(topic_file),
                    date=datetime.fromtimestamp(topic_file.stat().st_mtime).isoformat()[:10],
                    type="md",
                    status="enriched",
                    workflowStage="enrichment",
                    stageBadge=STAGE_BADGE_BY_WORKFLOW["enrichment"],
                    creatorName="topic_splitter",
                    sourcePlatform="pipeline",
                    contentType="topic",
                    contentId=f"topic:{topic_file.stem}",
                    sourcePath=str(topic_file),
                    manifestPath=None,
                    summary="AI 分割的话题内容",
                    tags=["enrichment", "topic"],
                    sourceType="local",
                    sourceGroupId=None,
                    sourceGroupName=None,
                    fileTimestamp=datetime.fromtimestamp(topic_file.stat().st_mtime).isoformat(),
                    fileType="文本",
                    sourceName=topic_file.stem,
                    semanticTitle="",
                ))

    elif workflow_stage in ["library", "parsing"]:
        for data, mp in manifests_data:
            assets.append(build_manifest_asset(data, mp, workflow_stage, evidence_paths, candidate_paths, approved_paths))

    elif workflow_stage in ["extraction", "review"]:
        processed_contents = set()
        for cp in candidate_paths:
            content_id = None
            payload = read_json_file(cp)
            if payload:
                if isinstance(payload, dict) and "review_payload" in payload:
                    content_id = payload.get("content_id")
                else:
                    first_event = payload[0] if isinstance(payload, list) else payload
                    content_id = first_event.get("content_id") if isinstance(first_event, dict) else None

            if not content_id:
                content_id = re.sub(r'(_events?\.json|\.review\.json)$', '', cp.name, flags=re.IGNORECASE)

            if content_id in processed_contents:
                continue
            processed_contents.add(content_id)

            manifest_tuple = manifests_by_content_id.get(content_id)
            if not manifest_tuple:
                manifest_tuple = manifests_by_source_name.get(re.sub(r'(_events?\.json|\.review\.json)$', '', cp.name, flags=re.IGNORECASE))

            manifest = manifest_tuple[0] if manifest_tuple else None

            review_payload = None
            if payload and isinstance(payload, dict) and "review_payload" in payload:
                raw_rp = payload["review_payload"]
                review_payload = ReviewPayload(
                    ticker=raw_rp.get("ticker", "待确认标的"),
                    direction=raw_rp.get("direction", "watchlist"),
                    timeHorizon=raw_rp.get("timeHorizon", "weekly"),
                    rationale=raw_rp.get("rationale", ""),
                    evidenceText=raw_rp.get("evidenceText", ""),
                    confidence=raw_rp.get("confidence", 0.84),
                    tags=raw_rp.get("tags", []),
                    ambiguityNotes=raw_rp.get("ambiguityNotes", []),
                    actionChain=[
                        ReviewActionPayload(**act) for act in raw_rp.get("actionChain", [])
                    ]
                )
            else:
                review_payload = build_review_payload_from_candidate(cp)

            tokens = build_match_tokens(content_id, manifest.get("title") if manifest else None, manifest.get("source_path") if manifest else None)
            evidence_path = first_matching_path(evidence_paths, tokens)
            approved_event_path = first_matching_path(approved_paths, tokens)

            source_type, group_id, group_name = extract_source_info(manifest, manifest.get("source_path") if manifest else str(cp))
            file_timestamp = extract_file_timestamp(manifest, cp)

            # Build semantic display fields
            evidence_preview = read_preview(evidence_path) if evidence_path else None
            display_info = build_display_info(
                file_name=manifest.get("title") if manifest else cp.name,
                extension="json",
                source_group_name=group_name,
                content_text=evidence_preview,
            )

            assets.append(AssetFile(
                id=content_id,
                name=manifest.get("title") if manifest else cp.name,
                size=format_file_size(cp),
                date=manifest.get("published_at", "")[:10] if manifest else datetime.fromtimestamp(cp.stat().st_mtime).isoformat()[:10],
                type="json",
                status="approved" if approved_event_path else ("needs review" if workflow_stage == "review" else "candidate ready"),
                workflowStage=workflow_stage,
                stageBadge=STAGE_BADGE_BY_WORKFLOW[workflow_stage],
                creatorName=manifest.get("creator_name", "unknown") if manifest else "unknown",
                sourcePlatform=manifest.get("source_platform", "pipeline") if manifest else "pipeline",
                contentType=manifest.get("content_type", "candidate_event") if manifest else "candidate_event",
                contentId=content_id,
                sourcePath=manifest.get("source_path", str(cp)) if manifest else str(cp),
                manifestPath=str(manifest_tuple[1]) if manifest_tuple else None,
                evidencePath=str(evidence_path) if evidence_path else None,
                candidateEventPath=str(cp),
                approvedEventPath=str(approved_event_path) if approved_event_path else None,
                summary=review_payload.evidence_text if review_payload and review_payload.evidence_text else (read_preview(evidence_path) or "Candidate event extracted."),
                tags=review_payload.tags if review_payload else [manifest.get("content_type", "candidate_event") if manifest else "candidate_event"],
                reviewPayload=review_payload or build_fallback_review_payload("Candidate missing.", []),
                sourceType=source_type,
                sourceGroupId=group_id,
                sourceGroupName=group_name,
                fileTimestamp=file_timestamp,
                fileType=display_info["fileType"],
                sourceName=display_info["sourceName"],
                semanticTitle=display_info["semanticTitle"],
            ))

        # fallback for manifests with no candidates
        for data, mp in manifests_data:
            if data.get("content_id") not in processed_contents:
                assets.append(build_manifest_asset(data, mp, workflow_stage, evidence_paths, candidate_paths, approved_paths))

    elif workflow_stage == "backtest":
        for bp in backtest_paths:
            file_timestamp = extract_file_timestamp(None, bp)
            bt_display_info = build_display_info(
                file_name=bp.name,
                extension=file_type_for(str(bp)),
                enable_semantic_title=False,
            )
            assets.append(AssetFile(
                id=f"backtest:{bp.name}",
                name=bp.name,
                size=format_file_size(bp),
                date=datetime.fromtimestamp(bp.stat().st_mtime).isoformat()[:10],
                type=file_type_for(str(bp)),
                status="backtest artifact",
                workflowStage="backtest",
                stageBadge=STAGE_BADGE_BY_WORKFLOW["backtest"],
                creatorName="system",
                sourcePlatform="backtester",
                contentType="backtest_result",
                contentId=bp.stem,
                sourcePath=str(bp),
                summary=read_preview(bp) or "Backtest output generated by the research evaluation layer.",
                tags=["backtest", file_type_for(str(bp))],
                sourceType="local",
                fileTimestamp=file_timestamp,
                fileType=bt_display_info["fileType"],
                sourceName=bt_display_info["sourceName"],
                semanticTitle="",
            ))

    # sort by file_timestamp if available, otherwise by date
    def sort_key(a: AssetFile) -> str:
        return a.file_timestamp or a.date or ""
    assets.sort(key=sort_key, reverse=True)
    return assets
