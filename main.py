"""
Main Pipeline - LangGraph Orchestration
Supports: Web Scraping, OCR (scanned journals), Social Media (Twitter/Facebook), TV Broadcast
Architecture Fix applied: Flattened the DAG to prevent unsynchronized fan-in collisions.
"""

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from schema_state import AgentState, merge_dicts

# Initialize Environment
load_dotenv()

# --- CENTRALIZED LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pipeline.main")

# --- NODE IMPORTS ---
from nodes.update_check_node import update_check_node
from nodes.scraper import scraper_node
from nodes.ocr import ocr_node
from nodes.keyword_filter_node import keyword_filter_node
from nodes.social_media_node import social_media_node
from nodes.capture_audio import capture_audio_node
from nodes.audio_to_txt import transcribe_audio_file


# --- COMPOSITE NODE: TV PIPELINE ---
async def process_tv_node(state: AgentState) -> dict:
    """
    Composite Node: Combines capture and transcription.
    """
    logger.info("[Composite TV] Phase 1: Capturing Audio...")
    capture_updates = await capture_audio_node(state)
    
    # Synthesize intermediate state
    intermediate_state = state.copy()
    intermediate_state.update(capture_updates)
    if "metadata" in capture_updates:
        intermediate_state["metadata"] = merge_dicts(state.get("metadata", {}), capture_updates.get("metadata"))

    # Extract file path
    metadata = intermediate_state.get("metadata", {})
    audio_file_path = metadata.get("audio_file_path")

    logger.info("[Composite TV] Phase 2: Transcribing Audio...")
    
    # Call the sync helper function properly (no 'await' because it's a standard 'def')
    articles_list = transcribe_audio_file(audio_file_path, channel_name=metadata.get("channel_name", "TV"))

    # Extract text from the articles list to update raw_content
    full_text = " ".join([art.get("text", "") for art in articles_list])

    # Package into the exact dictionary format LangGraph expects for State updates
    transcription_updates = {
        "raw_content": full_text,
        "scraped_articles": articles_list,  # Appends to list via operator.add reducer!
        "metadata": {
            "transcription_status": "success" if articles_list else "failed",
            "transcription_length": len(full_text)
        }
    }

    # Combine updates from both phases
    final_updates = {**capture_updates, **transcription_updates}
    if "metadata" in capture_updates or "metadata" in transcription_updates:
        meta_left = capture_updates.get("metadata", {})
        meta_right = transcription_updates.get("metadata", {})
        final_updates["metadata"] = merge_dicts(meta_left, meta_right)

    return final_updates


# --- CLASSIFIER STUB NODE ---
async def classifier_node(state: AgentState) -> dict:
    """Stub for downstream ML Classifier."""
    metadata = state.get("metadata") or {}
    logger.info("Executing Classifier stub node...")
    return {
        "metadata": {**metadata, "classifier_status": "stub_executed"},
        "is_harmful": False,
        "risk_score": 0.0,
        "human_review_status": "approved",
        "reasoning": "Mock classification passed."
    }


# --- ROUTING FUNCTIONS ---
def route_from_update(state: AgentState) -> list[str]:
    """Routes to appropriate source nodes based on input_types."""
    metadata = state.get("metadata") or {}
    
    input_types = metadata.get("input_types", [])
    if isinstance(input_types, str):
        input_types = [input_types]
        
    if not input_types:
        logger.warning("No input_types found. Aborting workflow.")
        return ["end"]
        
    routes = []
    
    # Route to our composite node instead of just capture
    if "tv_broadcast" in input_types:
        routes.append("process_tv")
    if "scanned_journal" in input_types:
        routes.append("ocr")
    if "social" in input_types:
        routes.append("social_media")
    if "web" in input_types:
        routes.append("scraper")
        
    if not routes:
        logger.warning("No valid ingestion routes found. Aborting workflow.")
        return ["end"]
        
    logger.info(f"Routing to: {routes}")
    return routes


def route_after_filter(state: AgentState) -> str:
    """Routes to classifier if keyword matches exist, else terminates."""
    metadata = state.get("metadata") or {}
    if not metadata.get("kw_match"):
        logger.info("Routing: No keyword matches found. Terminating graph.")
        return "end"
        
    logger.info("Routing: Keywords matched. Directing to Classifier.")
    return "classifier"


# --- GRAPH CONSTRUCTION ---
graph = StateGraph(AgentState)

# Register ALL nodes
graph.add_node("update_check", update_check_node)
graph.add_node("process_tv", process_tv_node)  # Using the new composite node
graph.add_node("scraper", scraper_node)
graph.add_node("ocr", ocr_node)
graph.add_node("social_media", social_media_node)
graph.add_node("keyword_filter", keyword_filter_node)
graph.add_node("classifier", classifier_node)

graph.set_entry_point("update_check")

# --- CONDITIONAL ROUTING FROM UPDATE_CHECK ---
graph.add_conditional_edges(
    "update_check",
    route_from_update,
    {
        "process_tv": "process_tv",
        "ocr": "ocr",
        "social_media": "social_media",
        "scraper": "scraper",
        "end": END
    }
)

# --- PERFECTLY SYNCHRONIZED FAN-IN ---
# Because every branch is exactly ONE node deep, they all finish together 
# and transition to keyword_filter exactly once.
graph.add_edge("process_tv", "keyword_filter")
graph.add_edge("scraper", "keyword_filter")
graph.add_edge("ocr", "keyword_filter")
graph.add_edge("social_media", "keyword_filter")

# --- FINAL CONDITIONAL ROUTING ---
graph.add_conditional_edges(
    "keyword_filter",
    route_after_filter,
    {
        "classifier": "classifier",
        "end": END
    }
)

graph.add_edge("classifier", END)

# Compile Application
workflow = graph.compile()


# --- EXECUTION TEST HARNESS ---
if __name__ == "__main__":
    async def run_pipeline():
        logger.info("Starting pipeline test run...")
        
        initial_state = {
            "source_name": "Multi-Source Feed",
            "source_type": "multi",
            "timestamp": datetime.now(),
            "raw_content": "",
            "metadata": {
                "input_types": ["tv_broadcast"], # add "social" or "scanned_journal" or "web" to test other branches but social is broken for now 
                "stream_url": "https://youtu.be/VGG2r3v6j_A?si=mWiqsDY9FKEB2lsM",
                "is_youtube": True,
                "duration_seconds": 15,
                "channel_name": "Al Jazeera Test",
                "social_platform": "twitter",
                "scrape_mode": "profiles",
                "target_profiles": ["ennaharonline"],
                "keywords": ["الجزائر", "وزير", "المحروقات"],
                "social_post_limit": 10
            },
            "scraped_articles": [],
            "matched_articles": [],
            "is_harmful": False,
            "risk_score": 0.0,
            "reasoning": "",
            "human_review_status": "pending"
        }
        
        result = await workflow.ainvoke(initial_state)
        
        logger.info("================ FINAL PIPELINE OUTPUT ================")
        logger.info(f"Source Name  : {result.get('source_name')}")
        logger.info(f"Review Status: {result.get('human_review_status')}")
        
        metadata = result.get("metadata", {})
        logger.info(f"Metadata Keys: {list(metadata.keys())}")
        
    asyncio.run(run_pipeline())