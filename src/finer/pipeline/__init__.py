"""Pipeline package.

Canonical F3→F4→F5 execution lives in ``finer.pipeline.canonical_runner``
(import it directly). The deprecated L0-L8 ``PipelineOrchestrator`` is no
longer re-exported here — importing ``finer.pipeline`` must not load the
quarantined orchestrator module (it lazily imports the legacy direct
extractor). Reach it explicitly via ``finer.pipeline.orchestrator`` if a
migration task truly needs it.

Legacy storage helpers stay re-exported for the CLI:
    from finer.pipeline import init_storage, register_directory
"""

# Re-export legacy storage/dry-run helpers from finer.pipeline._legacy
# (still used by cli.py init-storage / register-dir / dry-run).
from finer.pipeline._legacy import (
    init_storage,
    register_directory,
    run_perception_pipeline,
    dry_run_pipeline,
)

__all__ = [
    "init_storage",
    "register_directory",
    "run_perception_pipeline",
    "dry_run_pipeline",
]
