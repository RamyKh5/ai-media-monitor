"""
AgentState Schema - Defines the state structure for the LangGraph pipeline.
Includes defensive reducers for metadata merging (critical for parallel execution).
"""
from typing import Annotated, TypedDict, Optional, Literal, List, Dict, Any
from datetime import datetime
import operator

# --- CUSTOM DEFENSIVE REDUCER FOR METADATA ---
def merge_dicts(left: dict, right: Optional[dict]) -> dict:
    """
    Merge two dictionaries, guarding against NoneType.
    Without this, parallel branches overwrite each other's metadata, 
    and None returns cause fatal TypeError crashes.
    """
    if not right:  # Defensive check: if node returns no metadata, keep existing
        return left
    return {**left, **right}

# --- METADATA TYPEDICT ---
class Metadata(TypedDict, total=False):
    # Web scraping
    url: str
    keywords: List[str]
    update_status: str
    scrape_success: bool
    kw_match: bool
    
    # Social media
    social_platform: str
    scrape_mode: str
    target_profiles: List[str]
    social_post_limit: int
    social_scrape_status: str
    
    # Audio capture (TV)
    stream_url: str
    is_youtube: bool
    duration_seconds: int
    channel_name: str
    audio_file_path: str
    audio_capture_status: str
    audio_file_size: int
    audio_duration: int
    
    # Transcription
    transcription_status: str
    transcription_length: int
    transcription_error: str

    # Synthesis Output
    synthesizer_status: str
    synthesizer_file_path: str
    
    # General
    input_types: List[str]  # Supports parallel routing
    total_articles_extracted: int
    total_matched: int
    error: str
    reasoning: str
    classifier_status: str

# --- MAIN AGENTSTATE ---
class AgentState(TypedDict):
    # Context
    source_name: str
    source_type: Literal['journal', 'web', 'social', 'tv', 'scanned_journal', 'multi']
    timestamp: datetime
    
    # Payload
    raw_content: str
    
    # --- METADATA WITH DEFENSIVE REDUCER ---
    metadata: Annotated[dict, merge_dicts]
    
    # Pipeline data with reducers
    scraped_articles: Annotated[List[Dict[str, Any]], operator.add]
    matched_articles: Annotated[List[Dict[str, Any]], operator.add]
    
    # Intelligence
    is_harmful: bool
    risk_score: float
    reasoning: str
    
    # Output
    synthesis: Optional[str]
    human_review_status: Literal['pending', 'approved', 'rejected']