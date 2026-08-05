import asyncio
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from twscrape import API, gather
from socialapis import Facebook

# Assuming AgentState is defined elsewhere
from schema_state import AgentState

# ============================================================
# LOGGING SETUP
# ============================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

# ============================================================
# CONFIGURATION & CLIENTS
# ============================================================
SOCIALAPIS_API_TOKEN = os.getenv("SOCIALAPIS_API_TOKEN")
TWITTER_API: Optional[API] = None

def get_twitter_api() -> API:
    """Initialize twscrape API once and reuse."""
    global TWITTER_API
    if TWITTER_API is None:
        TWITTER_API = API()
        # PRO TIP: In production, ensure twscrape pool has accounts loaded.
    return TWITTER_API

def get_facebook_client() -> Facebook:
    """Initialize socialapis Facebook client."""
    if not SOCIALAPIS_API_TOKEN:
        raise ValueError("SOCIALAPIS_API_TOKEN is missing from environment variables.")
    return Facebook(api_token=SOCIALAPIS_API_TOKEN)

# ============================================================
# TWITTER SCRAPER
# ============================================================
async def fetch_twitter_by_keywords(keywords: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    if not keywords:
        return []
    
    query = " OR ".join(keywords)
    api = get_twitter_api()
    
    try:
        tweets = await gather(api.search(query, limit=limit))
        return [
            {
                "id": str(tweet.id),
                "author": tweet.user.username,
                "content": tweet.rawContent,
                "date": tweet.date.isoformat() if tweet.date else datetime.now().isoformat(),
                "url": tweet.url,
                "source": "twitter",
                "platform": "twitter"
            }
            for tweet in tweets
        ]
    except Exception as e:
        logger.error(f"Twitter search failed for query '{query}': {e}", exc_info=True)
        # We don't raise here; we return empty so the agent pipeline doesn't completely crash,
        # but the error is properly logged.
        return []

async def fetch_twitter_by_profiles(handles: List[str], limit: int = 30) -> List[Dict[str, Any]]:
    if not handles:
        return []
    
    all_tweets = []
    api = get_twitter_api()
    
    for handle in handles:
        clean_handle = handle.replace("@", "").strip()
        try:
            tweets = await gather(api.user_tweets(clean_handle, limit=limit))
            for tweet in tweets:
                all_tweets.append({
                    "id": str(tweet.id),
                    "author": tweet.user.username,
                    "content": tweet.rawContent,
                    "date": tweet.date.isoformat() if tweet.date else datetime.now().isoformat(),
                    "url": tweet.url,
                    "source": "twitter",
                    "platform": "twitter"
                })
        except Exception as e:
            logger.warning(f"Failed to fetch Twitter profile '{clean_handle}': {e}")
            continue
            
    return all_tweets

# ============================================================
# FACEBOOK SCRAPER
# ============================================================
def _normalize_fb_post(post: Any, source_handle: str = "Unknown") -> Optional[Dict[str, Any]]:
    is_dict = isinstance(post, dict)
    content = post.get('text', post.get('message', '')) if is_dict else getattr(post, 'text', getattr(post, 'message', ''))
    
    if not content:
        return None

    # Guarantee an ID exists for idempotency downstream
    post_id = str(post.get('id', '')) if is_dict else str(getattr(post, 'id', ''))
    if not post_id:
        post_id = f"fb_missing_id_{hash(content)}"

    return {
        "id": post_id,
        "author": post.get('page_name', post.get('author', source_handle)) if is_dict else getattr(post, 'page_name', getattr(post, 'author', source_handle)),
        "content": content,
        "date": post.get('created_time', datetime.now().isoformat()) if is_dict else getattr(post, 'created_time', datetime.now().isoformat()),
        "url": post.get('permalink_url', '') if is_dict else getattr(post, 'permalink_url', ''),
        "likes": post.get('likes', 0) if is_dict else getattr(post, 'likes', 0),
        "comments": post.get('comments', 0) if is_dict else getattr(post, 'comments', 0),
        "shares": post.get('shares', 0) if is_dict else getattr(post, 'shares', 0),
        "source": "facebook",
        "platform": "facebook"
    }

async def fetch_facebook_by_keywords(keywords: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    if not keywords or not SOCIALAPIS_API_TOKEN:
        return []
    
    if len(keywords) > 5:
        logger.warning(f"Truncating keywords from {len(keywords)} to 5 to respect Facebook API rate limits.")
        keywords = keywords[:5]
    
    def _sync_fetch():
        fb = get_facebook_client()
        results = []
        
        for keyword in keywords:
            try:
                safe_limit = min(max(1, limit // len(keywords)), 9)
                try:
                    posts = fb.search_posts(query=keyword, limit=safe_limit)
                except AttributeError:
                    posts = fb.get_page_posts(keyword, limit=safe_limit)

                if isinstance(posts, dict) and posts.get("success") is False:
                    logger.error(f"API Error for kw '{keyword}': {posts.get('detail')}")
                    # If it's an auth/quota error, we should ideally break here, not continue.
                    if "token" in str(posts.get('detail')).lower():
                        break 
                    continue
                    
                if not posts or not isinstance(posts, list):
                    continue
                    
                for post in posts:
                    normalized = _normalize_fb_post(post, source_handle=keyword)
                    if normalized:
                        results.append(normalized)
                        
            except Exception as e:
                logger.warning(f"Facebook search for '{keyword}' failed: {e}")
                continue
                
        return results
        
    return await asyncio.to_thread(_sync_fetch)

async def fetch_facebook_by_profiles(handles: List[str], limit: int = 30) -> List[Dict[str, Any]]:
    if not handles or not SOCIALAPIS_API_TOKEN:
        return []
        
    handles = [h.replace("@", "").strip() for h in handles]
    
    if len(handles) > 5:
        logger.warning(f"Truncating Facebook profiles from {len(handles)} to 5 to prevent rate limits.")
        handles = handles[:5]
    
    def _sync_fetch():
        fb = get_facebook_client()
        results = []

        for handle in handles:
            try:
                safe_limit = min(max(1, limit // len(handles)), 9)
                posts = fb.get_page_posts(handle, limit=safe_limit)

                if isinstance(posts, dict) and posts.get("success") is False:
                    logger.error(f"API Error for profile '{handle}': {posts.get('detail')}")
                    continue

                if not posts or not isinstance(posts, list):
                    continue

                for post in posts:
                    if isinstance(post, str):
                        results.append({
                            "id": f"fb_str_{hash(post)}", 
                            "author": handle, 
                            "content": post, 
                            "date": datetime.now().isoformat(), 
                            "url": "",
                            "likes": 0, "comments": 0, "shares": 0, 
                            "source": "facebook", "platform": "facebook"
                        })
                    else:
                        normalized = _normalize_fb_post(post, source_handle=handle)
                        if normalized:
                            results.append(normalized)

            except Exception as e:
                logger.warning(f"Facebook profile '{handle}' failed: {e}")
                continue

        return results
        
    return await asyncio.to_thread(_sync_fetch)

# ============================================================
# ROUTER & LANGGRAPH NODE
# ============================================================
async def social_media_node(state: AgentState) -> dict:
    metadata = state.get("metadata", {})
    
    platform = metadata.get("social_platform")
    mode = metadata.get("scrape_mode")
    keywords = metadata.get("keywords", [])
    profiles = metadata.get("target_profiles", [])
    limit = metadata.get("social_post_limit", 50)
    
    # Input Validation Guardrails
    if not platform or not mode:
        error_msg = f"Missing platform/mode. Got: platform={platform}, mode={mode}"
        logger.error(error_msg)
        return {"scraped_articles": [], "metadata": {**metadata, "social_scrape_status": "error", "error": error_msg}, "reasoning": error_msg}
    
    if mode == "keywords" and not keywords:
        return {"scraped_articles": [], "metadata": {**metadata, "social_scrape_status": "error", "error": "Missing keywords"}, "reasoning": "Missing keywords"}
    
    if mode == "profiles" and not profiles:
        return {"scraped_articles": [], "metadata": {**metadata, "social_scrape_status": "error", "error": "Missing profiles"}, "reasoning": "Missing profiles"}
    
    logger.info(f"Scraping {platform} in {mode} mode (limit={limit})")
    
    raw_posts = []
    try:
        if platform == "twitter":
            raw_posts = await fetch_twitter_by_keywords(keywords, limit) if mode == "keywords" else await fetch_twitter_by_profiles(profiles, limit)
        elif platform == "facebook":
            raw_posts = await fetch_facebook_by_keywords(keywords, limit) if mode == "keywords" else await fetch_facebook_by_profiles(profiles, limit)
        else:
            raise ValueError(f"Unsupported platform: {platform}")
            
    except Exception as e:
        logger.critical(f"Social extraction completely failed for {platform}: {e}")
        return {"scraped_articles": [], "metadata": {**metadata, "social_scrape_status": "failed", "error": str(e)}, "reasoning": f"Failed: {e}"}
    
    if not raw_posts:
        return {"scraped_articles": [], "metadata": {**metadata, "social_scrape_status": "success", "total_extracted": 0}, "reasoning": f"No posts from {platform}"}
    
    # Format for downstream nodes
    standardized_posts = [
        {
            "article_id": post.get("id"), # USING REAL ID INSTEAD OF ENUMERATION
            "selector": post.get("author", "Unknown"),
            "text": post.get("content", ""),
            "source": post.get("source", "social_media"),
            "platform": post.get("platform", "unknown"),
            "url": post.get("url", ""),
            "date": post.get("date", ""),
            "likes": post.get("likes", 0),
            "comments": post.get("comments", 0),
            "shares": post.get("shares", 0)
        }
        for post in raw_posts
    ]
    
    logger.info(f"Normalized {len(standardized_posts)} posts")
    
    return {
        "scraped_articles": standardized_posts,
        "metadata": {**metadata, "social_scrape_status": "success", "total_extracted": len(standardized_posts)},
        "reasoning": f"Extracted {len(standardized_posts)} posts from {platform}"
    }