from typing import TypedDict, Optional, Literal, List, Dict, Any
from datetime import datetime

# Structured metadata dictionary
class Metadata(TypedDict, total=False):
    author: str
    url: str
    language: str
    keywords: List[str]          # Pipeline needs this
    update_status: str           # Pipeline needs this
    scrape_success: bool         # Pipeline needs this
    kw_match: bool               # Pipeline needs this
    file_path: str               # OCR: PDF file path
    input_type: str              # "web" or "scanned_journal"
    total_articles_extracted: int
    total_matched: int
    extra_info: str

# Main AgentState schema
class AgentState(TypedDict):
    # Context
    source_name: str
    source_type: Literal['journal', 'web', 'social', 'tv']
    timestamp: datetime
    
    # Payload
    raw_content: str
    metadata: Optional[Metadata]
    
    # --- PIPELINE DATA (This is what you missed) ---
    scraped_articles: List[Dict[str, Any]]
    matched_articles: List[Dict[str, Any]]
    
    # Intelligence
    is_harmful: bool
    risk_score: float
    reasoning: str
    
    # Output
    synthesis: Optional[str]
    human_review_status: Literal['pending', 'approved', 'rejected']