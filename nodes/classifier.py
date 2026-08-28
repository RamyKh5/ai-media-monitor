import os
import json
import logging
import asyncio
from typing import Dict, Any, List
from pathlib import Path

from ollama import AsyncClient
from schema_state import AgentState

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
MODEL_NAME = os.getenv("CLASSIFIER_MODEL", "qwen2.5:7b")
TEMPERATURE = 0.0
MAX_ARTICLES_PER_RUN = 50
MAX_CONCURRENT_REQUESTS = 3  # Cap local inference parallelism to protect VRAM

# Initialize Async Ollama Client
async_ollama = AsyncClient()

CLASSIFICATION_PROMPT = """You are a content-risk classifier for Algerian news articles.
Analyze the article in its original language (Arabic, French, or English) and classify it into exactly ONE category.

CATEGORIES:
- SAFE: Regular news reporting, political commentary, event coverage.
- THREAT_OR_INCITEMENT: Calls to violence, targeted harm, mobilization, infrastructure disruption.
- MISINFORMATION_HAZARD: Disinformation designed to cause public panic or safety hazards.

Return ONLY a valid JSON object matching this schema:
{{
  "classification": "SAFE | THREAT_OR_INCITEMENT | MISINFORMATION_HAZARD",
  "confidence_score": 0.0,
  "reasoning": "Brief explanation."
}}

Article:
{article_text}"""


def truncate_safely(text: str, max_chars: int = 3000) -> str:
    """Truncates text safely without breaking mid-word."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    return truncated.rsplit(" ", 1)[0] + "..."


async def classify_single_article(article_text: str, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    """Asynchronously classifies a single article with concurrency throttling."""
    async with semaphore:
        truncated_text = truncate_safely(article_text)
        prompt = CLASSIFICATION_PROMPT.format(article_text=truncated_text)

        try:
            # Native JSON enforcement via Ollama format='json'
            response = await async_ollama.chat(
                model=MODEL_NAME,
                messages=[{'role': 'user', 'content': prompt}],
                format="json",
                options={'temperature': TEMPERATURE}
            )
            
            raw_content = response['message']['content']
            parsed = json.loads(raw_content)

            classification = parsed.get("classification", "UNKNOWN").strip()
            valid_categories = {"SAFE", "THREAT_OR_INCITEMENT", "MISINFORMATION_HAZARD"}
            
            if classification not in valid_categories:
                classification = "UNKNOWN"

            return {
                "classification": classification,
                "confidence_score": float(parsed.get("confidence_score", 0.0)),
                "reasoning": str(parsed.get("reasoning", "")),
                "raw_response": raw_content
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error: {e}")
            return {"classification": "PARSE_ERROR", "confidence_score": 0.0, "reasoning": str(e)}
        except Exception as e:
            logger.error(f"Ollama API Error: {e}")
            return {"classification": "API_ERROR", "confidence_score": 0.0, "reasoning": str(e)}


async def classifier_node(state: AgentState) -> dict:
    """LangGraph Async Node: Processes matched articles in parallel batches."""
    metadata = state.get("metadata") or {}
    matched_articles = state.get("matched_articles", [])

    if not matched_articles:
        logger.info("No articles to classify. Skipping classifier.")
        return {
            "metadata": {**metadata, "classifier_status": "skipped"},
            "reasoning": "Classifier skipped: empty input."
        }

    # Apply safety batch limits
    articles_to_process = matched_articles[:MAX_ARTICLES_PER_RUN]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    logger.info(f"Classifying {len(articles_to_process)} articles concurrently...")

    # Execute classifications in parallel while respecting concurrency cap
    tasks = [
        classify_single_article(art.get("text", ""), semaphore)
        for art in articles_to_process
    ]
    results = await asyncio.gather(*tasks)

    # Aggregate outputs into new article dicts (Immutability pattern)
    classified_articles = []
    summary = {"SAFE": 0, "THREAT_OR_INCITEMENT": 0, "MISINFORMATION_HAZARD": 0, "UNKNOWN": 0, "ERROR": 0}

    for orig_article, res in zip(articles_to_process, results):
        updated_article = {
            **orig_article,
            "classification": res["classification"],
            "confidence_score": res["confidence_score"],
            "classifier_reasoning": res["reasoning"]
        }
        classified_articles.append(updated_article)
        
        c_type = res["classification"] if res["classification"] in summary else "UNKNOWN"
        summary[c_type] += 1

    needs_review = (summary["THREAT_OR_INCITEMENT"] > 0 or summary["MISINFORMATION_HAZARD"] > 0)
    
    return {
        "matched_articles": classified_articles,
        "human_review_status": "pending" if needs_review else "approved",
        "reasoning": f"Found {summary['THREAT_OR_INCITEMENT']} threats, {summary['MISINFORMATION_HAZARD']} misinfo.",
        "metadata": {
            **metadata,
            "classifier_status": "success",
            "classifier_summary": summary
        }
    }