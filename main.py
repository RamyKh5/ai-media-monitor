"""
Main Pipeline - LangGraph Orchestration
Supports: Web Scraping, OCR (scanned journals), Social Media (Twitter/Facebook), TV Broadcast
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
from nodes.classifier import classifier_node


# --- COMPOSITE NODE: TV PIPELINE ---
async def process_tv_node(state: AgentState) -> dict:
    """Composite Node: Combines capture and transcription."""
    logger.info("[Composite TV] Phase 1: Capturing Audio...")
    capture_updates = await capture_audio_node(state)
    
    intermediate_state = state.copy()
    intermediate_state.update(capture_updates)
    if "metadata" in capture_updates:
        intermediate_state["metadata"] = merge_dicts(state.get("metadata", {}), capture_updates.get("metadata"))

    metadata = intermediate_state.get("metadata", {})
    audio_file_path = metadata.get("audio_file_path")

    logger.info("[Composite TV] Phase 2: Transcribing Audio...")
    articles_list = transcribe_audio_file(audio_file_path, channel_name=metadata.get("channel_name", "TV"))
    full_text = " ".join([art.get("text", "") for art in articles_list])

    transcription_updates = {
        "raw_content": full_text,
        "scraped_articles": articles_list,
        "metadata": {
            "transcription_status": "success" if articles_list else "failed",
            "transcription_length": len(full_text)
        }
    }

    final_updates = {**capture_updates, **transcription_updates}
    if "metadata" in capture_updates or "metadata" in transcription_updates:
        meta_left = capture_updates.get("metadata", {})
        meta_right = transcription_updates.get("metadata", {})
        final_updates["metadata"] = merge_dicts(meta_left, meta_right)

    return final_updates


# --- SYNTHESIZER STUB NODE ---
async def synthesizer_node(state: AgentState) -> dict:
    """
    Final Node for SAFE articles: Generates a daily brief.
    Currently a stub. To be implemented next.
    """
    logger.info("Executing Synthesizer stub node on SAFE articles...")
    metadata = state.get("metadata") or {}
    matched_articles = state.get("matched_articles", [])
    
    synthesis_text = f"Synthesized report for {len(matched_articles)} safe articles."
    
    return {
        "metadata": {**metadata, "synthesizer_status": "success"},
        "reasoning": synthesis_text
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


def route_after_classifier(state: AgentState) -> str:
    """
    Routes based on the Human Review Status output by the Classifier.
    """
    status = state.get("human_review_status")
    if status == "pending":
        logger.warning("Routing: Threats/Misinfo found. Sending to Human Review Queue (END).")
        return "end"
    
    logger.info("Routing: Batch approved as SAFE. Directing to Synthesizer.")
    return "synthesizer"


# --- GRAPH CONSTRUCTION ---
graph = StateGraph(AgentState)

graph.add_node("update_check", update_check_node)
graph.add_node("process_tv", process_tv_node) 
graph.add_node("scraper", scraper_node)
graph.add_node("ocr", ocr_node)
graph.add_node("social_media", social_media_node)
graph.add_node("keyword_filter", keyword_filter_node)
graph.add_node("classifier", classifier_node) 
graph.add_node("synthesizer", synthesizer_node)

graph.set_entry_point("update_check")

# --- ROUTING EDGES ---
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

# Perfectly synchronized fan-in
graph.add_edge("process_tv", "keyword_filter")
graph.add_edge("scraper", "keyword_filter")
graph.add_edge("ocr", "keyword_filter")
graph.add_edge("social_media", "keyword_filter")

graph.add_conditional_edges(
    "keyword_filter",
    route_after_filter,
    {
        "classifier": "classifier",
        "end": END
    }
)

graph.add_conditional_edges(
    "classifier",
    route_after_classifier,
    {
        "synthesizer": "synthesizer",
        "end": END
    }
)

graph.add_edge("synthesizer", END)

workflow = graph.compile()


# --- EXECUTION TEST HARNESS ---
if __name__ == "__main__":
    async def run_pipeline():
        logger.info("Starting pipeline test run for OCR...")
        
        initial_state = {
            "source_name": "Scanned Newspaper Tests",
            "source_type": "journal",
            "timestamp": datetime.now(),
            "raw_content": "",
            "metadata": {
                # 1. SET THIS TO TRIGGER THE OCR ROUTE
                "input_types": ["scanned_journal"], 
                
                # 2. POINT THIS TO YOUR TEST IMAGE
                # Change this path to point to the specific SAFE or THREAT image you want to test
                "file_path": "./tests/03_threat_incitement.pdf", 
                
                # Keywords to trigger the filter node (ensure these exist in your test image!)
                "keywords": ["supporters", "messages", "violence"], 
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
        logger.info(f"Final Metadata: {metadata}")
        
        # Print the final classifications if any articles made it through
        if result.get("matched_articles"):
            logger.info("--- Classification Results ---")
            for art in result.get("matched_articles"):
                logger.info(f"Classification: {art.get('classification')} | Confidence: {art.get('confidence_score')}")
                logger.info(f"Reasoning: {art.get('classifier_reasoning')}")
        
    asyncio.run(run_pipeline())