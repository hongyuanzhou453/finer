import asyncio

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from finer.api.routes.asset_builder import build_workflow_assets

router = APIRouter()

@router.get("")
async def get_stats():
    # build_workflow_assets is a heavy synchronous scan (manifests + previews,
    # can be slow/LLM-backed on a cold cache). Offload to the threadpool and run
    # the three stages concurrently so a GET /api/stats never blocks the single
    # event loop (which would stall every other request, e.g. /radar).
    intake_a, library_a, review_a = await asyncio.gather(
        run_in_threadpool(build_workflow_assets, "intake"),
        run_in_threadpool(build_workflow_assets, "library"),
        run_in_threadpool(build_workflow_assets, "review"),
    )
    intake = len(intake_a)
    library = len(library_a)
    review = len(review_a)


    return {
        "success": True,
        "contract": "canonical_stats_v1",
        "pulse": {
            "intake": intake,
            "library": library,
            "review": review
        }
    }
