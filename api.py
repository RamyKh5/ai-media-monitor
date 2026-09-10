import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# this api.py must be in the same directory as main.py
from main import workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.jobs")

# --- JOB STORAGE 
job_database: Dict[str, Dict[str, Any]] = {}
job_lock = asyncio.Lock()
JOB_TTL_SECONDS = 3600

# --- PROGRESS MAPPING 
# We map LangGraph node names to completion percentages
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

# --- LIFESPAN MANAGER (Modern Startup/Shutdown) 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch the background cleanup task
    logger.info("API starting up. Launching cleanup task.")
    cleanup_task = asyncio.create_task(cleanup_old_jobs())
    
    yield # The API runs here
    
    # Shutdown: Cancel the task cleanly
    logger.info("API shutting down. Cancelling cleanup task.")
    cleanup_task.cancel()

app = FastAPI(title="Ministere Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all local frontend ports (e.g., localhost:3000, 5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REQUEST MODELS ---
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

# --- BACKGROUND TASK ---
async def run_pipeline_task(job_id: str, request: JobCreateRequest):
    logger.info(f"[Job {job_id}] Starting pipeline...")
    
    async with job_lock:
        job_database[job_id]["status"] = "running"
        job_database[job_id]["progress"] = 5
        job_database[job_id]["current_step"] = "initializing"
    
    try:
        initial_state = {
            "source_name": "API Upload",
            "metadata": {
                "input_types": request.input_types,
                "keywords": request.keywords,
                "file_path": request.file_path
            },
            "matched_articles": [],
            "human_review_status": "pending"
        }
        
        final_state = None
        
        # USE astream() TO GET REAL-TIME UPDATES FROM LANGGRAPH
        async for output in workflow.astream(initial_state):
            # output is a dict like {"ocr": {state_updates}}
            for node_name, state_update in output.items():
                progress_val = NODE_PROGRESS_MAP.get(node_name, job_database[job_id]["progress"])
                
                async with job_lock:
                    job_database[job_id]["progress"] = progress_val
                    job_database[job_id]["current_step"] = f"Running {node_name}"
                    
                # Keep track of the latest state to extract the file path at the end
                final_state = state_update
        
        # Extract the file path saved by the synthesizer
        saved_file = final_state.get("metadata", {}).get("synthesizer_file_path", "Path not found")
        
        async with job_lock:
            job_database[job_id]["status"] = "completed"
            job_database[job_id]["progress"] = 100
            job_database[job_id]["current_step"] = "done"
            job_database[job_id]["result_path"] = saved_file
            
        logger.info(f"[Job {job_id}] Completed successfully.")
        
    except Exception as e:
        logger.error(f"[Job {job_id}] Pipeline failed: {e}", exc_info=True)
        async with job_lock:
            job_database[job_id]["status"] = "failed"
            job_database[job_id]["error"] = str(e)
            job_database[job_id]["current_step"] = "failed"

# --- ENDPOINTS ---
@app.post("/api/jobs", response_model=JobStatusResponse)
async def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    print(f"\n[DEBUG] API Received Keywords: {request.keywords}\n") # debugg
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
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(job_id=job_id, **job)

# --- CLEANUP TASK ---
async def cleanup_old_jobs():
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