import re
import unicodedata
from schema_state import AgentState

def normalize_arabic(text: str) -> str:
    """
    Robust Arabic text normalization:
    - Strips diacritics (Tashkeel) and Tatweel
    - Normalizes Alef variations, Teh Marbuta, and Alef Maksura
    - Strips whitespace and lowercases
    """
    if not text:
        return ""
    
    # Remove Tashkeel (vowels/diacritics)
    tashkeel_pattern = re.compile(r'[\u0617-\u061A\u064B-\u0652]')
    text = re.sub(tashkeel_pattern, '', text)
    
    # Remove Tatweel (elongation character 'ـ')
    text = text.replace("ـ", "")
    
    # Normalize Alef forms (أ, إ, آ -> ا)
    text = re.sub(r'[أإآ]', 'ا', text)
    
    # Normalize Teh Marbuta to Heh (ة -> ه)
    text = re.sub(r'ة', 'ه', text)
    
    # Normalize Alef Maksura to Yeh (ى -> ي)
    text = re.sub(r'ى', 'ي', text)
    
    return text.strip().lower()

def keyword_filter_node(state: AgentState) -> dict:
    """
    Filters scraped articles using normalized keyword matching.
    """
    metadata = state.get("metadata") or {}
    articles = state.get("scraped_articles", [])

    # Clean and normalize target keywords
    raw_keywords = metadata.get("keywords", [])
    keywords = [normalize_arabic(k) for k in raw_keywords if k.strip()]

    if not keywords:
        return {
            "metadata": {**metadata, "kw_match": False, "kw_error": "Missing filter criteria"},
            "human_review_status": "rejected",
            "reasoning": "Pipeline stopped: No tracking keywords specified."
        }

    matched_articles = []
    
    for art in articles:
        text_norm = normalize_arabic(art["text"])
        
        # DEBUG: Print out the first 50 chars of normalized text to see what we're matching
        print(f"[DEBUG] Checking article snippet: {text_norm[:50]}...")

        # Identify matching keywords within this specific article
        matched_keys = [k for k in keywords if k in text_norm]

        if matched_keys:
            # Shallow copy article and decorate with matched keywords
            article_entry = dict(art)
            article_entry["matched_keywords"] = matched_keys
            matched_articles.append(article_entry)

    if matched_articles:
        return {
            "matched_articles": matched_articles,
            "metadata": {**metadata, "kw_match": True, "total_matched": len(matched_articles)},
            "reasoning": f"Successfully matched {len(matched_articles)} articles."
        }
    
    return {
        "matched_articles": [],
        "metadata": {**metadata, "kw_match": False},
        "human_review_status": "rejected",
        "reasoning": f"No target keywords matched. Evaluated keys: {keywords}"
    }