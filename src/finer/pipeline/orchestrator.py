"""Pipeline Orchestrator — **DEPRECATED** L0-L8 implementation.

.. deprecated::
    This module is deprecated. Use ``finer.pipeline.canonical_runner`` for
    the canonical F3→F4→F5 pipeline, or the F0-F8 orchestrator when available.

**IMPORTANT**: This orchestrator uses the deprecated L0-L8 naming and
pipeline structure. The canonical F0-F8 pipeline (F3→F4→F5 in particular)
is implemented in ``canonical_runner.py``.

- This module is preserved for backward compatibility with existing L0-L8
  data directories and ingestion workflows.
- New features and canonical-path work MUST target the F0-F8 pipeline,
  not extend this orchestrator.
- F3 Intent → F4 Policy → F5 Execute canonical chain lives in
  ``canonical_runner.py`` (via ``run_canonical_extraction()``).
- ``DEFAULT_STAGES`` below uses legacy L0-L8 naming. Canonical F0-F8
  pipeline uses ``canonical_runner.run_canonical_extraction()``.

Design principles:
- Each stage failure does NOT block subsequent stages (logged, continued)
- Supports skipping already-completed stages
- Respects layer isolation boundaries per CLAUDE.md
- All I/O is async; stage implementations may be sync (wrapped automatically)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from finer.paths import DATA_ROOT, REPO_ROOT

# Quarantine hard gate (P0 #1 单一真相源收口): importing this module is an
# error for new code — it lazily wires the legacy direct TradeActionExtractor
# and L0-L8 stage naming. Read-only migration tooling opts in explicitly with
# the same escape hatch that unlocks the legacy extractor entry.
if os.environ.get("FINER_ALLOW_LEGACY_PIPELINE", "").strip() != "1":
    raise ImportError(
        "finer.pipeline.orchestrator is quarantined (deprecated L0-L8 "
        "pipeline). Use finer.pipeline.canonical_runner / finer.pipeline."
        "driver. Set FINER_ALLOW_LEGACY_PIPELINE=1 only for read-only "
        "migration tooling."
    )

logger = logging.getLogger(__name__)


# =============================================================================
# Result Models
# =============================================================================

class StageResult(BaseModel):
    """Result of a single pipeline stage."""
    stage: str = Field(..., description="Stage identifier, e.g. 'L0', 'L1'")
    success: bool = Field(True, description="Whether the stage completed successfully")
    duration_ms: float = Field(0.0, description="Execution time in milliseconds")
    output_path: Optional[str] = Field(None, description="Path to stage output artifact")
    error: Optional[str] = Field(None, description="Error message if stage failed")
    skipped: bool = Field(False, description="Whether the stage was skipped (already completed)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Stage-specific metadata")


class PipelineResult(BaseModel):
    """Result of a full pipeline run for a single content item."""
    content_id: str
    stages_completed: List[str] = Field(default_factory=list)
    stages_failed: List[str] = Field(default_factory=list)
    stages_skipped: List[str] = Field(default_factory=list)
    trade_actions: List[Dict[str, Any]] = Field(default_factory=list)
    total_duration_ms: float = Field(0.0, description="Total pipeline wall time")
    error: Optional[str] = None
    stage_results: List[StageResult] = Field(default_factory=list)


class DateRange(BaseModel):
    """Date range for backtest pipeline."""
    start: str = Field(..., description="Start date (ISO 8601)")
    end: str = Field(..., description="End date (ISO 8601)")


class BacktestPipelineResult(BaseModel):
    """Result of the specialized backtest pipeline (L5→L8)."""
    kol_id: str
    date_range: DateRange
    actions_found: int = 0
    timeline_entries: int = 0
    backtest_completed: bool = False
    stages_completed: List[str] = Field(default_factory=list)
    stages_failed: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Stage Completion Tracker
# =============================================================================

class StageCompletionTracker:
    """Track which stages have completed for a given content_id.

    Uses marker files in data/.pipeline_state/ to persist completion state
    across runs, enabling skip-already-completed semantics.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or DATA_ROOT / ".pipeline_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def is_completed(self, content_id: str, stage: str) -> bool:
        """Check if a stage has already completed for a content item."""
        marker = self.state_dir / content_id / f"{stage}.done"
        return marker.exists()

    def mark_completed(self, content_id: str, stage: str) -> None:
        """Mark a stage as completed."""
        marker = self.state_dir / content_id / f"{stage}.done"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now().isoformat(), encoding="utf-8")

    def mark_failed(self, content_id: str, stage: str, error: str) -> None:
        """Mark a stage as failed (for diagnostics, does not block)."""
        marker = self.state_dir / content_id / f"{stage}.fail"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{datetime.now().isoformat()}\n{error}", encoding="utf-8")

    def clear(self, content_id: str) -> None:
        """Clear all state for a content item (re-run from scratch)."""
        import shutil
        state_path = self.state_dir / content_id
        if state_path.exists():
            shutil.rmtree(state_path)


# =============================================================================
# Pipeline Orchestrator
# =============================================================================

class PipelineOrchestrator:
    """Declarative pipeline orchestrator.

    Runs content through the Finer pipeline stages:
    - L0: Content registration (manifest creation)
    - L1: Enrichment (topic splitting, entity extraction, market data)
    - L3: Perception/parsing (OCR, ASR, text normalization)
    - L4: Aggregation (entity disambiguation, context aggregation)
    - L5: Extraction (trade action extraction)

    Each stage is independently callable and failures are non-blocking.
    """

    # Legacy stage order (deprecated L0-L8).
    # Canonical F0-F8 uses canonical_runner.run_canonical_extraction() instead.
    DEFAULT_STAGES = ["L0", "L1", "L3", "L4", "L5"]

    def __init__(
        self,
        root: Optional[Path] = None,
        skip_completed: bool = True,
    ):
        """Initialize the orchestrator.

        Args:
            root: Project root directory. Defaults to REPO_ROOT.
            skip_completed: Whether to skip stages already completed for
                a given content_id (based on marker files).
        """
        self.root = root or REPO_ROOT
        self.skip_completed = skip_completed
        self.tracker = StageCompletionTracker()

        # Stage registry — maps stage name to implementation
        self.stages: Dict[str, Callable] = {
            "L0": self._run_l0,
            "L1": self._run_l1,
            "L3": self._run_l3,
            "L4": self._run_l4,
            "L5": self._run_l5,
        }

    # =========================================================================
    # Public API
    # =========================================================================

    async def run_full_pipeline(
        self,
        content_id: str,
        stages: Optional[List[str]] = None,
        kol_id: Optional[str] = None,
        force: bool = False,
    ) -> PipelineResult:
        """Run the full pipeline for a single content item.

        Args:
            content_id: The content item to process.
            stages: Ordered list of stages to run. Defaults to DEFAULT_STAGES.
            kol_id: Optional KOL identifier for L1 enrichment context.
            force: If True, re-run all stages even if previously completed.

        Returns:
            PipelineResult with completion status for each stage.
        """
        if stages is None:
            stages = self.DEFAULT_STAGES

        start_time = time.time()
        result = PipelineResult(content_id=content_id)

        for stage_name in stages:
            if stage_name not in self.stages:
                logger.warning(f"Unknown stage '{stage_name}', skipping")
                result.stages_skipped.append(stage_name)
                continue

            # Skip already-completed stages unless forced
            if not force and self.skip_completed and self.tracker.is_completed(content_id, stage_name):
                logger.info(f"[{content_id}] Stage {stage_name} already completed, skipping")
                result.stages_skipped.append(stage_name)
                result.stage_results.append(StageResult(
                    stage=stage_name,
                    skipped=True,
                ))
                continue

            # Run the stage
            stage_result = await self._execute_stage(
                stage_name, content_id, kol_id=kol_id
            )
            result.stage_results.append(stage_result)

            if stage_result.skipped:
                result.stages_skipped.append(stage_name)
            elif stage_result.success:
                result.stages_completed.append(stage_name)
                self.tracker.mark_completed(content_id, stage_name)
            else:
                result.stages_failed.append(stage_name)
                self.tracker.mark_failed(content_id, stage_name, stage_result.error or "unknown")
                # Non-blocking: log and continue

        # Collect trade actions from L5 output
        l5_result = next(
            (r for r in result.stage_results if r.stage == "L5" and r.success),
            None,
        )
        if l5_result and l5_result.metadata.get("trade_actions"):
            result.trade_actions = l5_result.metadata["trade_actions"]

        result.total_duration_ms = (time.time() - start_time) * 1000
        return result

    async def run_batch_pipeline(
        self,
        content_ids: List[str],
        stages: Optional[List[str]] = None,
        kol_id: Optional[str] = None,
        force: bool = False,
        max_concurrency: int = 5,
    ) -> List[PipelineResult]:
        """Run the pipeline for multiple content items concurrently.

        Uses asyncio.Semaphore to limit concurrent tasks and avoid
        overwhelming system resources.

        Args:
            content_ids: List of content IDs to process.
            stages: Stages to run per item.
            kol_id: KOL identifier.
            force: Force re-run all stages.
            max_concurrency: Maximum concurrent pipeline runs (default: 5).

        Returns:
            List of PipelineResult, one per content_id.
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_with_limit(cid: str) -> PipelineResult:
            async with semaphore:
                return await self.run_full_pipeline(
                    content_id=cid,
                    stages=stages,
                    kol_id=kol_id,
                    force=force,
                )

        # Run all tasks concurrently with semaphore limit
        tasks = [run_with_limit(cid) for cid in content_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        final_results: List[PipelineResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append(
                    PipelineResult(
                        content_id=content_ids[i],
                        error=f"Pipeline failed: {r}",
                    )
                )
            else:
                final_results.append(r)

        return final_results

    async def run_backtest_pipeline(
        self,
        kol_id: str,
        date_range: DateRange,
    ) -> BacktestPipelineResult:
        """Run the specialized backtest pipeline: L5 products -> L7 timeline -> L8 backtest.

        This pipeline does NOT re-extract; it operates on existing L5
        trade action artifacts for a given KOL and date range.

        Args:
            kol_id: KOL identifier whose actions to backtest.
            date_range: Date range for backtest.

        Returns:
            BacktestPipelineResult with backtest status.
        """
        result = BacktestPipelineResult(kol_id=kol_id, date_range=date_range)

        # L7: Build timeline from L5 trade actions
        try:
            timeline = await self._run_l7_timeline(kol_id, date_range)
            result.timeline_entries = len(timeline)
            result.stages_completed.append("L7")
        except Exception as e:
            logger.error(f"L7 timeline failed for {kol_id}: {e}")
            result.stages_failed.append("L7")
            result.error = str(e)
            return result

        # L8: Run backtest
        try:
            backtest_ok = await self._run_l8_backtest(kol_id, date_range, timeline)
            result.backtest_completed = backtest_ok
            result.actions_found = sum(len(t.get("actions", [])) for t in timeline)
            result.stages_completed.append("L8")
        except Exception as e:
            logger.error(f"L8 backtest failed for {kol_id}: {e}")
            result.stages_failed.append("L8")
            if not result.error:
                result.error = str(e)

        return result

    # =========================================================================
    # Stage Execution
    # =========================================================================

    async def _execute_stage(
        self,
        stage_name: str,
        content_id: str,
        kol_id: Optional[str] = None,
    ) -> StageResult:
        """Execute a single pipeline stage with timing and error handling."""
        stage_fn = self.stages[stage_name]
        stage_start = time.time()

        try:
            metadata = await stage_fn(content_id, kol_id=kol_id)
            duration_ms = (time.time() - stage_start) * 1000

            return StageResult(
                stage=stage_name,
                success=True,
                duration_ms=duration_ms,
                output_path=metadata.get("output_path"),
                metadata=metadata,
            )
        except Exception as e:
            duration_ms = (time.time() - stage_start) * 1000
            logger.error(
                f"[{content_id}] Stage {stage_name} failed: {e}",
                exc_info=True,
            )
            return StageResult(
                stage=stage_name,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    # =========================================================================
    # Stage Implementations
    # =========================================================================

    async def _run_l0(
        self, content_id: str, *, kol_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """L0: Content registration.

        Loads the content manifest. If the manifest does not exist,
        the content has not been registered — this is a prerequisite.
        """
        manifest_path = self.root / "data" / "processed" / "manifests" / f"{content_id}.json"

        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Manifest not found for {content_id}. "
                "Content must be registered before running the pipeline."
            )

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        return {
            "output_path": str(manifest_path),
            "content_type": manifest.get("source_type") or manifest.get("content_type"),
            "creator_name": manifest.get("creator_name"),
            "source_path": manifest.get("raw_path") or manifest.get("source_path"),
        }

    async def _run_l1(
        self, content_id: str, *, kol_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """L1: Enrichment — topic splitting, entity extraction, market data fusion.

        Reads the content source, runs entity extraction and topic splitting,
        writes results to data/L1_enrichment/.
        """
        from finer.enrichment import TopicSplitter, EntityExtractor

        # Load manifest to get source path
        manifest_path = self.root / "data" / "processed" / "manifests" / f"{content_id}.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        source_path = Path(manifest.get("raw_path") or manifest.get("source_path"))
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Read content text
        content_text = ""
        if source_path.suffix in (".json",):
            with open(source_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                content_text = data.get("text", data.get("content", ""))
        else:
            try:
                content_text = source_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content_text = ""

        if not content_text:
            logger.warning(f"[{content_id}] L1: No text content available for enrichment")
            return {"output_path": None, "topics": [], "entities": []}

        # Entity extraction (always available)
        entity_extractor = EntityExtractor()
        entities = entity_extractor.extract(content_text)

        # Topic splitting (only for long content)
        topic_splitter = TopicSplitter()
        topics = topic_splitter.split(content_text)

        # Persist enrichment results
        output_dir = self.root / "data" / "L1_enrichment"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{content_id}_enrichment.json"

        enrichment_data = {
            "content_id": content_id,
            "enriched_at": datetime.now().isoformat(),
            "entities": {
                "tickers": entities.tickers,
                "companies": entities.companies,
                "people": entities.people,
                "events": entities.events,
                "concepts": entities.concepts,
                "metrics": entities.metrics,
            },
            "topics": [
                {
                    "title": t.title,
                    "tickers": t.tickers,
                    "companies": t.companies,
                    "summary": t.summary,
                }
                for t in topics
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(enrichment_data, f, indent=2, ensure_ascii=False)

        return {
            "output_path": str(output_path),
            "topics_count": len(topics),
            "entities_count": len(entities.tickers) + len(entities.companies),
        }

    async def _run_l3(
        self, content_id: str, *, kol_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """L3: Perception/parsing — OCR, ASR, text normalization.

        Uses PerceptionOrchestrator to convert raw content into
        standardized research objects.
        """
        from finer.services.perception import PerceptionOrchestrator

        # Load manifest
        manifest_path = self.root / "data" / "processed" / "manifests" / f"{content_id}.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        source_path = Path(manifest.get("raw_path") or manifest.get("source_path"))
        content_type = manifest.get("source_type") or manifest.get("content_type", "text")

        orchestrator = PerceptionOrchestrator()
        research_obj = orchestrator.process_content(
            source_path=source_path,
            content_id=content_id,
            content_type=content_type,
        )

        if research_obj is None:
            raise RuntimeError(f"Perception orchestrator returned None for {content_id}")

        # Save research object
        research_dir = self.root / "data" / "processed" / "research_objects"
        research_dir.mkdir(parents=True, exist_ok=True)
        output_path = research_dir / f"{content_id}_research.json"
        orchestrator.save_research_object(research_obj, output_path)

        return {
            "output_path": str(output_path),
            "parsing_status": research_obj.get("parsing_status", "unknown"),
        }

    async def _run_l4(
        self, content_id: str, *, kol_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """L4: Aggregation — entity disambiguation, context aggregation.

        Uses L4AggregationLayer to resolve entities and build context.
        """
        from finer.aggregation import create_l4_layer

        # Load L3 output (research object) for text content
        research_path = self.root / "data" / "processed" / "research_objects" / f"{content_id}_research.json"

        # Fall back to L1 enrichment if L3 output not available
        text = ""
        if research_path.exists():
            with open(research_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                text = data.get("summary", "")
                # Also check for raw_text in nine_grid
                if not text:
                    text = data.get("nine_grid_evaluation", {}).get("fundamental", {}).get("view", "")
        else:
            # Try reading from L1 enrichment
            enrichment_path = self.root / "data" / "L1_enrichment" / f"{content_id}_enrichment.json"
            if enrichment_path.exists():
                with open(enrichment_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Use topic summaries as text
                    summaries = [t.get("summary", "") for t in data.get("topics", []) if t.get("summary")]
                    text = " ".join(summaries)

        if not text:
            logger.warning(f"[{content_id}] L4: No text available for aggregation")
            return {"output_path": None, "entities": []}

        layer = create_l4_layer()
        context = layer.process_text(
            text=text,
            content_id=content_id,
            author=kol_id,
        )

        # Persist L4 output
        output_dir = self.root / "data" / "L4_parsed"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{content_id}_aggregated.json"

        aggregated_data = {
            "content_id": content_id,
            "aggregated_at": datetime.now().isoformat(),
            "entities": [
                {
                    "raw_text": e.raw_text,
                    "normalized": e.normalized,
                    "entity_type": e.entity_type,
                    "confidence": e.confidence,
                    "market": e.market,
                }
                for e in context.entities
            ],
            "summary": context.summary,
            "cross_references": context.cross_references,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(aggregated_data, f, indent=2, ensure_ascii=False)

        return {
            "output_path": str(output_path),
            "entities_count": len(context.entities),
            "cross_references_count": len(context.cross_references),
        }

    async def _run_l5(
        self, content_id: str, *, kol_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """L5: Extraction — trade action extraction from parsed content.

        Uses TradeActionExtractor to extract trade actions from L4 output.
        """
        # Load L4 aggregated output
        l4_path = self.root / "data" / "L4_parsed" / f"{content_id}_aggregated.json"

        # Fall back to L3/L1 if L4 not available
        text = ""
        source_for_extraction = "L4"
        if l4_path.exists():
            with open(l4_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Use summary or entity context
                parts = []
                if data.get("summary"):
                    parts.append(data["summary"])
                for entity in data.get("entities", []):
                    parts.append(f"{entity.get('raw_text', '')} ({entity.get('normalized', '')})")
                text = " ".join(parts)
        else:
            # Try L3 research object
            research_path = self.root / "data" / "processed" / "research_objects" / f"{content_id}_research.json"
            if research_path.exists():
                with open(research_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    text = data.get("summary", "")
                    source_for_extraction = "L3"
            else:
                # Try L1 enrichment
                enrichment_path = self.root / "data" / "L1_enrichment" / f"{content_id}_enrichment.json"
                if enrichment_path.exists():
                    with open(enrichment_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        summaries = [t.get("summary", "") for t in data.get("topics", []) if t.get("summary")]
                        text = " ".join(summaries)
                        source_for_extraction = "L1"

        if not text:
            logger.warning(f"[{content_id}] L5: No text available for extraction")
            return {"output_path": None, "trade_actions": []}

        # Attempt to use TradeActionExtractor
        try:
            from finer.extraction.trade_action_extractor import TradeActionExtractor

            # DEPRECATED: Use canonical_action_builder via golden_path.py instead
            extractor = TradeActionExtractor(enable_enrichment=True)
            context = {
                "source_id": content_id,
                "author": kol_id,
            }
            result = await extractor.extract_from_text(text, context)

            if result.success and result.actions:
                actions_data = [a.model_dump(mode="json") for a in result.actions]
            else:
                actions_data = []
                logger.warning(
                    f"[{content_id}] L5: Extraction returned no actions: {result.error}"
                )
        except ImportError:
            logger.warning("TradeActionExtractor not available, L5 extraction skipped")
            actions_data = []

        # Persist L5 output
        output_dir = self.root / "data" / "L5_candidate"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{content_id}_actions.json"

        extraction_data = {
            "content_id": content_id,
            "extracted_at": datetime.now().isoformat(),
            "source_stage": source_for_extraction,
            "actions": actions_data,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(extraction_data, f, indent=2, ensure_ascii=False)

        return {
            "output_path": str(output_path),
            "trade_actions": actions_data,
            "actions_count": len(actions_data),
        }

    # =========================================================================
    # Backtest Pipeline Stages (L7, L8)
    # =========================================================================

    async def _run_l7_timeline(
        self, kol_id: str, date_range: DateRange
    ) -> List[Dict[str, Any]]:
        """L7: Build timeline from L5 trade actions for a KOL.

        Reads L5_candidate/*.json, filters by kol_id and date range,
        and constructs a timeline suitable for backtesting.
        """
        l5_dir = self.root / "data" / "L5_candidate"
        if not l5_dir.exists():
            return []

        timeline = []
        for action_file in sorted(l5_dir.glob("*.json")):
            try:
                with open(action_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                actions = data.get("actions", [])
                if not actions:
                    continue

                # Filter by date range
                extracted_at = data.get("extracted_at", "")
                if extracted_at:
                    if extracted_at < date_range.start or extracted_at > date_range.end:
                        continue

                timeline.append({
                    "content_id": data.get("content_id"),
                    "extracted_at": extracted_at,
                    "actions": actions,
                })
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to read L5 file {action_file}: {e}")
                continue

        # Persist timeline
        timeline_dir = self.root / "data" / "L7_model_results"
        timeline_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = timeline_dir / f"{kol_id}_timeline.json"
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump({
                "kol_id": kol_id,
                "date_range": date_range.model_dump(),
                "entries": timeline,
                "created_at": datetime.now().isoformat(),
            }, f, indent=2, ensure_ascii=False)

        return timeline

    async def _run_l8_backtest(
        self,
        kol_id: str,
        date_range: DateRange,
        timeline: List[Dict[str, Any]],
    ) -> bool:
        """L8: Run backtest on timeline.

        Placeholder implementation — writes timeline to L8_metrics
        and returns True. Full backtest engine integration is future work.
        """
        if not timeline:
            logger.info(f"L8: No timeline entries for {kol_id}, backtest skipped")
            return False

        metrics_dir = self.root / "data" / "L8_metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = metrics_dir / f"{kol_id}_backtest.json"

        backtest_data = {
            "kol_id": kol_id,
            "date_range": date_range.model_dump(),
            "total_actions": sum(len(t.get("actions", [])) for t in timeline),
            "status": "completed",
            "backtest_at": datetime.now().isoformat(),
            "note": "Placeholder — full backtest engine integration pending",
        }

        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(backtest_data, f, indent=2, ensure_ascii=False)

        logger.info(f"L8: Backtest result saved to {metrics_path}")
        return True

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_available_stages(self) -> List[str]:
        """Return the list of registered stage names."""
        return list(self.stages.keys())

    def get_content_status(self, content_id: str) -> Dict[str, bool]:
        """Return completion status for each stage of a content item."""
        return {
            stage: self.tracker.is_completed(content_id, stage)
            for stage in self.stages
        }

    def reset_content(self, content_id: str) -> None:
        """Clear all pipeline state for a content item."""
        self.tracker.clear(content_id)
