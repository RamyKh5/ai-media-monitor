import os
import aiohttp
import logging
from datetime import datetime
from schema_state import AgentState

# Instantiate logger for this module
logger = logging.getLogger("pipeline.update_check")

async def update_check_node(state: AgentState) -> dict:
    """
    Source-aware change detector:
    - For 'social': Bypasses checks (real-time stream).
    - For 'scanned_journal': Verifies the local PDF file exists on disk.
    - For 'web': Checks HTTP headers (Last-Modified / ETag) to prevent redundant scrapes.
    """
    metadata = state.get("metadata") or {}
    input_type = metadata.get("input_type", "web")

    # BRANCH 0: Social Media (Fastest check, zero I/O)
    if input_type == "social":
        logger.info("Skipping update check for social media source.")
        return {"metadata": {**metadata, "update_status": "proceed"}}

    # BRANCH 1: Local PDF / Scanned Journal Input
    if input_type == "scanned_journal":
        file_path = metadata.get("file_path")
        
        if not file_path:
            logger.warning("OCR route selected, but no 'file_path' provided in metadata.")
            return {
                "metadata": {**metadata, "update_status": "validation_failed"},
                "human_review_status": "rejected",
                "reasoning": "Update check failed: Missing local PDF file path."
            }
        
        if not os.path.exists(file_path):
            logger.error(f"Target PDF file not found at disk path: '{file_path}'")
            return {
                "metadata": {**metadata, "update_status": "validation_failed"},
                "human_review_status": "rejected",
                "reasoning": f"Update check failed: Cannot locate file at '{file_path}'."
            }

        # File exists on disk; safe to route to OCR
        logger.info(f"Local PDF verified at '{file_path}'. Ready for OCR processing.")
        return {
            "metadata": {
                **metadata, 
                "update_status": "proceed",
                "file_checked_at": datetime.now().isoformat()
            }
        }

    # BRANCH 2: Web Scraping Input
    url = metadata.get("url")
    if not url:
        logger.warning("Web scraper route selected, but no 'url' provided in metadata.")
        return {
            "metadata": {**metadata, "update_error": "No URL provided", "update_status": "validation_failed"},
            "human_review_status": "rejected",
            "reasoning": "Update check failed: No URL specified for web source."
        }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, headers=headers, timeout=10, allow_redirects=True) as resp:
                if resp.status >= 400:
                    logger.warning(f"HEAD request returned HTTP {resp.status}. Forcing web scrape.")
                    return {
                        "metadata": {
                            **metadata, 
                            "update_status": "proceed", # Unified status to move forward
                            "http_code": resp.status
                        }
                    }

                last_modified = resp.headers.get("Last-Modified")
                etag = resp.headers.get("ETag")

                if not last_modified and not etag:
                    logger.info("No caching headers found. Forcing full web scrape.")
                    return {
                        "metadata": {**metadata, "update_status": "proceed"}
                    }

                prev_mod = metadata.get("last_modified")
                prev_etag = metadata.get("etag")

                if last_modified == prev_mod and etag == prev_etag:
                    logger.info("Web content unchanged since last run.")
                    return {"metadata": {**metadata, "update_status": "unchanged"}}

                logger.info("Web content updated or new. Proceeding to scrape.")
                return {
                    "metadata": {
                        **metadata,
                        "last_modified": last_modified,
                        "etag": etag,
                        "update_status": "proceed",
                        "update_checked_at": datetime.now().isoformat()
                    }
                }
    except Exception as e:
        logger.error(f"HEAD request failed: {e}. Defaulting to forced scrape.")
        return {
            "metadata": {
                **metadata, 
                "update_error": str(e), 
                "update_status": "proceed"
            }
        }