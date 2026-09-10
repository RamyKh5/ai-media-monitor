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

# IMPORT THE NEW SYNTHESIZER
from nodes.synthesizer import consume_and_process, PipelineConfig, ArticleInput


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


# --- SYNTHESIZER NODE (INTEGRATED) ---
async def synthesizer_node(state: AgentState) -> dict:
    """
    Final Node for SAFE articles: Generates a daily brief.
    Acts as an adapter between the Graph State dicts and the Synthesizer Pydantic models.
    """
    logger.info("Executing Synthesizer node on SAFE articles...")
    metadata = state.get("metadata", {})
    matched_articles = state.get("matched_articles", [])
    
    if not matched_articles:
        logger.warning("Synthesizer reached, but no matched articles found to summarize.")
        return {"metadata": {**metadata, "synthesizer_status": "skipped"}}

    # ADAPTER LOGIC: Map state dictionaries to ArticleInput models
    article_inputs = []
    for i, art in enumerate(matched_articles):
        article_inputs.append(
            ArticleInput(
                article_id=art.get("id", f"ocr_art_{i}"),
                text=art.get("text", ""), 
                source=metadata.get("source_name", "Scanned Journal"),
                language="ar" # Enforce Arabic synthesis
            )
        )
    
    # Configure specifically for your CPU hardware constraints
    config = PipelineConfig(
        model_name="qwen2.5:3b-instruct", 
        max_concurrent_batches=1,
        max_articles_per_batch=5
    )
    
    # Execute the async pipeline
    logger.info(f"Passing {len(article_inputs)} verified articles to Synthesis Engine...")
    await consume_and_process(article_inputs, config)
    #Construct the path where the synthesizer saved the markdown file
    today_str = datetime.now().strftime("%Y_%m_%d")
    report_path = f"data/syntheses/daily_synthesis_{today_str}.md"
    return {
        "metadata": {**metadata, "synthesizer_status": "success", "synthesizer_file_path": report_path},
        "reasoning": f"Successfully synthesized {len(article_inputs)} articles into daily brief."
    }


# --- ROUTING FUNCTIONS ---
def route_from_update(state: AgentState) -> list[str]:
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
    metadata = state.get("metadata") or {}
    if not metadata.get("kw_match"):
        logger.info("Routing: No keyword matches found. Terminating graph.")
        return "end"
        
    logger.info("Routing: Keywords matched. Directing to Classifier.")
    return "classifier"


def route_after_classifier(state: AgentState) -> str:
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
        logger.info("Starting pipeline test run for OCR to Synthesizer...")
        
        initial_state = {
            "source_name": "Scanned Newspaper Tests",
            "source_type": "journal",
            "timestamp": datetime.now(),
            "raw_content": "",
            "metadata": {
                "input_types": ["scanned_journal"], 
                
                # IMPORTANT: CHANGE THIS TO A BENIGN/SAFE PDF TO REACH THE SYNTHESIZER
                "file_path": "./tests/02_mixed_pipeline_test.pdf", 
                
                # Pick 2-3 words that actually exist in your safe document so it passes the filter
                "keywords": ["االعتداء", "االستثمار", "انهيار", "الغابات"], 
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
        logger.info(f"Synthesizer Status: {metadata.get('synthesizer_status', 'Not reached')}")
        
    asyncio.run(run_pipeline())