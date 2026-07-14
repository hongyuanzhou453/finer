"""Background pipeline auto-driver (roadmap direction ①, 2026-07-13).

Turns the manual ``finer.cli pipeline-drive --watch`` foreground loop into a
real refresh cycle owned by the API server: on startup, an interruptible async
loop periodically runs :func:`finer.pipeline.driver.drive_once`, so newly
imported F0 content flows F1→F1.5→F2→F5→(F8 auto-backtest)→settle and shows up
on the leaderboard/radar without a human launching a script.

Design constraints (see docs/specs/2026-07-13-next-optimization-directions.md):

* **Opt-in.** Disabled by default. Enabling it makes the server perform real
  LLM-backed extraction and *apply* settle writes on a timer, so it must be an
  explicit ``FINER_PIPELINE_AUTODRIVE=1`` choice, never a side effect of
  starting the server (tests/CI must stay inert).
* **Non-blocking.** ``drive_once`` is synchronous and heavy; it runs in a worker
  thread via ``asyncio.to_thread`` so the event loop and request handling are
  never blocked.
* **Serialized.** One loop awaits each pass before sleeping — passes never
  overlap, so two drives can't race on the same envelope.
* **Isolated.** A failing pass is logged and recorded, never propagated: one bad
  cycle must not kill the loop.

The orchestration truth stays in ``pipeline/driver.py``; this module only
schedules it. ``server.py`` wires start/stop into the FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from finer.config import PipelineAutoDriveConfig, load_pipeline_autodrive_config

logger = logging.getLogger(__name__)


class PipelineAutoDriver:
    """Owns the background drive loop and exposes its status."""

    def __init__(self, config: Optional[PipelineAutoDriveConfig] = None) -> None:
        self.config = config or load_pipeline_autodrive_config()
        self._task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()
        self.runs = 0
        self.last_run_at: Optional[str] = None
        self.last_report: Optional[dict[str, Any]] = None
        self.last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spawn the background loop if enabled; otherwise a logged no-op."""
        if not self.config.enabled:
            logger.info(
                "pipeline auto-driver disabled "
                "(set FINER_PIPELINE_AUTODRIVE=1 to enable)"
            )
            return
        if self.running:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="pipeline-autodrive")
        logger.info(
            "pipeline auto-driver started (interval=%ds settle=%s limit=%s)",
            self.config.interval_seconds,
            self.config.run_settle,
            self.config.limit,
        )

    async def stop(self) -> None:
        """Signal and cancel the loop, waiting for it to unwind cleanly."""
        self._stopping.set()
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("pipeline auto-driver stopped after %d run(s)", self.runs)

    async def _sleep_or_stop(self, seconds: float) -> bool:
        """Wait ``seconds`` unless stop is requested first.

        Returns True if a stop was requested during the wait.
        """
        if seconds <= 0:
            return self._stopping.is_set()
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _loop(self) -> None:
        # Let startup (router registration, cache warmup) settle before the
        # first heavy pass; abort early if stopped during the delay.
        if await self._sleep_or_stop(self.config.initial_delay_seconds):
            return
        while not self._stopping.is_set():
            await self.run_pass()
            if await self._sleep_or_stop(self.config.interval_seconds):
                return

    async def run_pass(self) -> Optional[dict[str, Any]]:
        """Run one incremental drive_once in a worker thread; isolate failures."""
        from finer.pipeline.driver import drive_once

        self.runs += 1
        self.last_run_at = datetime.now().isoformat()
        try:
            report = await asyncio.to_thread(
                drive_once,
                limit=self.config.limit,
                run_settle=self.config.run_settle,
                dry_run=False,
            )
            self.last_report = report.to_dict()
            self.last_error = None
            logger.info(
                "auto-drive pass %d: scanned=%d f1=%d f2=%d f5=%d reconciled=%d failures=%d",
                self.runs,
                report.scanned,
                report.f1_ran,
                report.f2_ran,
                report.f5_ran,
                len(report.reconciled),
                len(report.failures),
            )
            return self.last_report
        except Exception as exc:  # noqa: BLE001 — a bad pass must not kill the loop
            self.last_error = f"{type(exc).__name__}: {exc}"[:500]
            logger.exception("auto-drive pass %d failed", self.runs)
            return None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "running": self.running,
            "interval_seconds": self.config.interval_seconds,
            "limit": self.config.limit,
            "run_settle": self.config.run_settle,
            "runs": self.runs,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "last_report": self.last_report,
        }
