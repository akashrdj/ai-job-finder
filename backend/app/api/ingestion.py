from fastapi import APIRouter, BackgroundTasks
from typing import Dict, Any
from app.scheduler.scheduler_service import scheduler_service
from app.config import settings

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])

@router.post("/run")
async def trigger_ingestion_pipeline(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Trigger manual execution of the end-to-end ingestion, matching, and drafting pipeline.
    """
    if scheduler_service.is_running:
        return {
            "status": "already_running",
            "message": "Pipeline is currently executing in background."
        }

    # Run in background task to avoid blocking HTTP request
    background_tasks.add_task(scheduler_service.execute_full_pipeline)
    return {
        "status": "started",
        "message": "Pipeline run dispatched successfully."
    }

@router.get("/status")
async def get_pipeline_status() -> Dict[str, Any]:
    """
    Get live scheduler status, active adapters, and last execution metrics.
    """
    return {
        "scheduler_active": scheduler_service.scheduler.running,
        "is_currently_running": scheduler_service.is_running,
        "interval_minutes": settings.INGESTION_INTERVAL_MINUTES,
        "min_score_threshold": settings.MIN_MATCH_SCORE_FOR_DRAFTING,
        "llm_provider": settings.LLM_PROVIDER,
        "last_run_time": scheduler_service.last_run_time.isoformat() if scheduler_service.last_run_time else None,
        "last_run_stats": scheduler_service.last_run_stats,
        "active_sources": list(scheduler_service.ingestion_manager.adapters.keys())
    }
