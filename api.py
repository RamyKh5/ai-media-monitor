import os
import json
import shutil
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse

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

# --- FILE UPLOAD DIRECTORY ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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


# --- INTERNAL REQUEST MODEL ---
# We build this from FormData inside the endpoint.
# It's NOT a Pydantic model because it's never parsed from HTTP directly.
class JobRequest:
    def __init__(
        self,
        input_types: List[str],
        keywords: List[str],
        file_path: Optional[str]
    ):
        self.input_types = input_types
        self.keywords = keywords
        self.file_path = file_path


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


# --- RESPONSE SCHEMA ---
class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    current_step: str = ""
    result_path: Optional[str] = None
    error: Optional[str] = None


# --- BACKGROUND WORKER TASK ---
async def run_pipeline_task(job_id: str, request: JobRequest):
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

        # Stream node updates in real-time
        async for output in workflow.astream(initial_state):
            for node_name, state_update in output.items():

                progress_val = NODE_PROGRESS_MAP.get(
                    node_name,
                    job_database[job_id]["progress"]
                )

                async with job_lock:
                    job_database[job_id]["progress"] = progress_val
                    job_database[job_id]["current_step"] = f"Running {node_name}"

                # Deep merge: preserves nested metadata keys from all nodes
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
async def create_job(
    background_tasks: BackgroundTasks,
    input_types: str = Form(...),              # JSON string: '["scanned_journal"]'
    keywords: str = Form(...),                 # JSON string: '["pénurie","carburant"]'
    file: Optional[UploadFile] = File(None),   # Binary file upload
    file_path: Optional[str] = Form(None),     # URL / path for non-file jobs
):
    """
    Accepts multipart/form-data (from the frontend's FormData).
    Parses JSON strings back into Python lists.
    Saves uploaded files to disk.
    """
    # --- PARSE FORM FIELDS ---
    try:
        input_types_list = json.loads(input_types)
        keywords_list = json.loads(keywords)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON in form fields: {e}"
        )

    logger.info(
        f"Job creation request received. "
        f"Types: {input_types_list}, Keywords: {keywords_list}"
    )

    # --- SAVE UPLOADED FILE IF PROVIDED ---
    saved_path: Optional[str] = None

    if file is not None:
        # Preserve the original file extension (e.g., .pdf, .png)
        ext = os.path.splitext(file.filename or "")[1]
        safe_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = os.path.join(UPLOAD_DIR, safe_name)

        # Stream file to disk (memory-safe for large uploads)
        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"Saved uploaded file to: {saved_path}")

    # Use uploaded file if present; otherwise fall back to file_path (URL)
    effective_file_path = saved_path or file_path

    # --- CREATE JOB ---
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

    # --- BUILD INTERNAL REQUEST ---
    pipeline_request = JobRequest(
        input_types=input_types_list,
        keywords=keywords_list,
        file_path=effective_file_path
    )

    # --- RUN IN BACKGROUND ---
    background_tasks.add_task(run_pipeline_task, job_id, pipeline_request)

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