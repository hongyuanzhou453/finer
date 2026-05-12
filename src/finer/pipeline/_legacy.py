"""Legacy pipeline functions — Backward compatible synchronous API.

These functions were originally in ``finer.pipeline`` (single-file module).
They are preserved here for backward compatibility with CLI and other callers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finer.config import load_creator_config
from finer.manifests import register_file
from finer.paths import ensure_storage

from finer.services.perception import PerceptionOrchestrator


def init_storage(root: Path) -> dict[str, Any]:
    created = ensure_storage(root)
    return {
        "status": "ok",
        "created_or_verified": created,
    }


def register_directory(
    *,
    root: Path,
    creator_id: str,
    content_type: str,
    source_dir: Path,
    pattern: str,
    dry_run: bool,
) -> dict[str, Any]:
    ensure_storage(root)
    creator_cfg = load_creator_config(root, creator_id)
    if content_type not in creator_cfg["content_types"]:
        raise ValueError(f"unsupported content type for {creator_id}: {content_type}")
    if not source_dir.exists():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    files = sorted([p for p in source_dir.glob(pattern) if p.is_file()])
    results = []
    for file_path in files:
        results.append(
            register_file(
                root=root,
                creator_id=creator_id,
                creator_name=creator_cfg["display_name"],
                source_type=content_type,
                source_platform="image_upload" if "image" in content_type else "bilibili",
                source_file=file_path,
                dry_run=dry_run,
            )
        )

    return {
        "status": "ok",
        "creator_id": creator_id,
        "content_type": content_type,
        "count": len(results),
        "items": results,
    }


def run_perception_pipeline(root: Path, dry_run: bool = False) -> dict[str, Any]:
    """
    Executes the perception stage (Step 1) for all registered content.
    Generates research objects in data/processed/research_objects.
    """
    ensure_storage(root)
    manifest_dir = root / "data" / "processed" / "manifests"
    research_dir = root / "data" / "processed" / "research_objects"
    research_dir.mkdir(parents=True, exist_ok=True)

    manifests = sorted(manifest_dir.glob("*.json"))
    orchestrator = PerceptionOrchestrator()
    results = []

    for manifest_path in manifests:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        content_id = manifest["content_id"]
        source_path = Path(manifest.get("raw_path") or manifest.get("source_path"))
        content_type = manifest.get("source_type") or manifest.get("content_type")

        if dry_run:
            results.append({"content_id": content_id, "status": "skipped_dry_run"})
            continue

        # Run the full perception orchestrator
        research_obj = orchestrator.process_content(
            source_path=source_path,
            content_id=content_id,
            content_type=content_type
        )

        if research_obj:
            output_path = research_dir / f"{content_id}_research.json"
            orchestrator.save_research_object(research_obj, output_path)
            results.append({"content_id": content_id, "status": "processed", "path": str(output_path)})

    return {
        "status": "ok",
        "count": len(results),
        "processed": results
    }


def dry_run_pipeline(root: Path) -> dict[str, Any]:
    ensure_storage(root)
    manifests = sorted((root / "data" / "processed" / "manifests").glob("*.json"))
    return {
        "status": "ok",
        "summary": {
            "manifests_found": len(manifests),
            "ocr_stage": "not_implemented",
            "asr_stage": "not_implemented",
            "extraction_stage": "not_implemented",
            "backtest_stage": "not_implemented",
        },
        "next_actions": [
            "integrate PaddleOCR for image parsing",
            "normalize OCR output into segment records",
            "implement candidate event extraction",
            "add Label Studio task export",
        ],
    }
