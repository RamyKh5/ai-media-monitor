import asyncio
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Literal
import sys
import io

from langgraph.graph import StateGraph, END
from schema_state import AgentState
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()
# --- 1. Centralized Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pipeline.main")

# --- Node Imports ---
from nodes.update_check_node import update_check_node
from nodes.scraper import scraper_node
from nodes.ocr import ocr_node
from nodes.keyword_filter_node import keyword_filter_node
from nodes.social_media_node import social_media_node  

# --- 2. Classifier Stub Node ---
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

# --- 3. Routing Functions (Control Flow) ---

def route_from_update(state: AgentState) -> str:
    metadata = state.get("metadata") or {}
    status = metadata.get("update_status")
    
    # 1. Catch all scenarios where we should NOT proceed
    if status in ["unchanged", "validation_failed"]:
        logger.info(f"Routing: Update status is '{status}'. Terminating graph.")
        return "end"
    
    # 2. Proceed to the correct node based on type
    input_type = metadata.get("input_type", "web")
    
    if input_type == "scanned_journal":
        return "ocr"
    elif input_type == "social":
        return "social_media"
    
    return "scraper"

def route_after_filter(state: AgentState) -> str:
    """Routes to classifier if keyword matches exist, else terminates."""
    metadata = state.get("metadata") or {}
    match = metadata.get("kw_match")
    
    if not match:
        logger.info("Routing: No keyword matches found. Terminating graph.")
        return "end"
        
    logger.info("Routing: Keywords matched. Directing to Classifier.")
    return "classifier"

# --- 4. Graph Construction ---
graph = StateGraph(AgentState)

# Register nodes
graph.add_node("update_check", update_check_node)
graph.add_node("scraper", scraper_node)
graph.add_node("ocr", ocr_node)
graph.add_node("keyword_filter", keyword_filter_node)
graph.add_node("classifier", classifier_node)
graph.add_node("social_media", social_media_node)
# Set entry point
graph.set_entry_point("update_check")

# Add conditional routing
graph.add_conditional_edges(
    "update_check",
    route_from_update,
    {
        "scraper": "scraper",
        "ocr": "ocr",
        "social_media": "social_media",
        "end": END
    }
)

# Fan-in edges to keyword filter
graph.add_edge("scraper", "keyword_filter")
graph.add_edge("ocr", "keyword_filter")
graph.add_edge("social_media", "keyword_filter") 

# Final conditional routing
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

# --- 5. Execution Test Harness ---
if __name__ == "__main__":
    async def run_pipeline():
        logger.info("Starting pipeline test run...")
        
        # Test state pointing to a PDF file path
        initial_state = {
         "source_name": "Social Media Feed",  # Changed
         "source_type": "social",              # Changed from "scanned_journal"
         "timestamp": datetime.now(),
         "raw_content": "",
         "metadata": {
             "input_type": "social",
             "social_platform": "facebook",
             "scrape_mode": "profiles",
             "target_profiles": ["ennaharonline", "algerie360"],
             "keywords": ["الجزائر", "وزير", "المحروقات"],
            "social_post_limit": 20
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
        logger.info(f"Reasoning    : {result.get('reasoning')}")
        logger.info(f"Metadata     : {result.get('metadata')}")
        
        matched = result.get("matched_articles", [])
        logger.info(f"Matched Articles Count: {len(matched)}")

    asyncio.run(run_pipeline())