from typing import TypedDict, Optional, Literal
from datetime import datetime

# Structured metadata dictionary
class Metadata(TypedDict, total=False):
    author: str
    url: str
    language: str
    extra_info: str  # optional catch-all

# Main AgentState schema
class AgentState(TypedDict):
    # Context
    source_name: str
    source_type: Literal['journal', 'web', 'social', 'tv']
    timestamp: datetime
    
    # Payload
    raw_content: str
    metadata: Optional[Metadata]
    
    # Intelligence
    is_harmful: bool
    risk_score: float
    reasoning: str
    
    # Output
    synthesis: Optional[str]
    human_review_status: Literal['pending', 'approved', 'rejected']
