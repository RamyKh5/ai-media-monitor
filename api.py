import os
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse  # <-- NEW IMPORT

# Ensure main.py is in the same directory and exports 'workflow'
from main import workflow

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.jobs")

# --- IN-MEMORY JOB STORAGE ---
# Senior Note: Suitable for local dev. Production requires Redis or PostgreSQL.
job_database: Dict[str, Dict[str, Any]] = {}
job_lock = asyncio.Lock()
JOB_TTL_SECONDS = 3600

# --- PROGRESS MAPPING ---
NODE_PROGRESS_MAP = {
    "update_check": 10,
    "ocr": 30,
    "scraper": 30,
    "process_tv": 30,
    "social_media": 30,
    "keyword_filter": 50,
    "classifier": 80,
    "synthesizer": 100
}


# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up. Launching cleanup task.")
    cleanup_task = asyncio.create_task(cleanup_old_jobs())
    yield
    logger.info("API shutting down. Cancelling cleanup task.")
    cleanup_task.cancel()


app = FastAPI(title="Ministere Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REQUEST & RESPONSE SCHEMAS ---
class JobCreateRequest(BaseModel):
    input_types: list[str]
    keywords: list[str] = []
    file_path: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    current_step: str = ""
    result_path: Optional[str] = None
    error: Optional[str] = None


# --- BACKGROUND WORKER TASK ---
async def run_pipeline_task(job_id: str, request: JobCreateRequest):
    """
    Executes the LangGraph pipeline asynchronously in the background.
    Safely captures exceptions to avoid crashing Uvicorn worker threads.
    """
    logger.info(f"[Job {job_id}] Starting pipeline execution...")

    async with job_lock:
        job_database[job_id]["status"] = "running"
        job_database[job_id]["progress"] = 5
        job_database[job_id]["current_step"] = "initializing"

    try:
        initial_state = {
            "source_name": "API Upload",
            "source_type": "multi",
            "timestamp": datetime.now(),
            "raw_content": "",
            "metadata": {
                "input_types": request.input_types,
                "keywords": request.keywords,
                "file_path": request.file_path
            },
            "scraped_articles": [],
            "matched_articles": [],
            "is_harmful": False,
            "risk_score": 0.0,
            "reasoning": "",
            "human_review_status": "pending"
        }

        final_state: Dict[str, Any] = {}

        async for output in workflow.astream(initial_state):
            for node_name, state_update in output.items():
                
                progress_val = NODE_PROGRESS_MAP.get(
                    node_name,
                    job_database[job_id]["progress"]
                )

                async with job_lock:
                    job_database[job_id]["progress"] = progress_val
                    job_database[job_id]["current_step"] = f"Running {node_name}"

                if isinstance(state_update, dict):
                    for key, value in state_update.items():
                        if isinstance(value, dict) and isinstance(final_state.get(key), dict):
                            final_state[key].update(value)
                        else:
                            final_state[key] = value

        saved_file = final_state.get("metadata", {}).get(
            "synthesizer_file_path",
            "Path not found"
        )

        async with job_lock:
            job_database[job_id]["status"] = "completed"
            job_database[job_id]["progress"] = 100
            job_database[job_id]["current_step"] = "done"
            job_database[job_id]["result_path"] = saved_file

        logger.info(f"[Job {job_id}] Completed successfully. Output: {saved_file}")

    except Exception as e:
        logger.error(f"[Job {job_id}] Pipeline execution failed: {e}", exc_info=True)

        async with job_lock:
            job_database[job_id]["status"] = "failed"
            job_database[job_id]["error"] = str(e)
            job_database[job_id]["current_step"] = "failed"


# --- ENDPOINTS ---
@app.get("/")
async def root_health_check():
    return {"status": "online", "system": "Cellule de Veille API"}
@app.post("/api/jobs", response_model=JobStatusResponse)
async def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    logger.info(f"Job creation request received with keywords: {request.keywords}")

    job_id = str(uuid.uuid4())

    async with job_lock:
        job_database[job_id] = {
            "status": "queued",
            "progress": 0,
            "current_step": "queued",
            "created_at": datetime.now().isoformat(),
            "result_path": None,
            "error": None
        }

    background_tasks.add_task(run_pipeline_task, job_id, request)
    return JobStatusResponse(job_id=job_id, status="queued")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    async with job_lock:
        job = job_database.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return JobStatusResponse(job_id=job_id, **job)


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """
    Streams the synthesis file back to the client.
    Uses FileResponse for async, non-blocking I/O.
    """
    async with job_lock:
        job = job_database.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Job is '{job['status']}'. You can only fetch results for completed jobs."
        )

    result_path = job.get("result_path")

    if not result_path or not os.path.exists(result_path):
        logger.error(f"File missing for job {job_id} at path: {result_path}")
        raise HTTPException(status_code=404, detail="Result file not found on the server.")

    # SENIOR UPGRADE: This streams the file directly to the client.
    # It automatically handles chunking and sets the correct HTTP headers.
    return FileResponse(
        path=result_path, 
        media_type="text/markdown", 
        filename=f"synthesis_result_{job_id}.md"
    )


# --- BACKGROUND GARBAGE COLLECTION ---
async def cleanup_old_jobs():
    """Periodically purges expired jobs from RAM to prevent memory leaks."""
    while True:
        await asyncio.sleep(300)
        now = datetime.now()
        async with job_lock:
            expired_ids = [
                jid for jid, job in job_database.items()
                if (now - datetime.fromisoformat(job["created_at"])).total_seconds() > JOB_TTL_SECONDS
            ]
            for jid in expired_ids:
                del job_database[jid]
                logger.info(f"Garbage collector removed expired job {jid}")