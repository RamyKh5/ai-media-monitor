import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # Correct class-based import
from schema_state import AgentState

async def scraper_node(state: AgentState) -> dict:
    metadata = state.get("metadata") or {}  # ← Defensive guard
    url = metadata.get("url")
    
    if not url:
        return {
            "scraped_articles": [],
            "metadata": {**metadata, "error": "No URL provided"},
            "human_review_status": "rejected" 
        }

    scraped_articles = []

    try:
        # Correct v2.x wrapper pattern using Stealth() class
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # Navigate with strict timeout
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")

            article_selectors = [
                "article", 
                "div.post-item", 
                "div.news-item", 
                ".card",
                "div.entry-content"
            ]

            found_elements = []
            for sel in article_selectors:
                locators = await page.locator(sel).all()
                if locators:
                    found_elements = locators
                    selected_selector = sel
                    break

            if found_elements:
                for idx, element in enumerate(found_elements):
                    try:
                        text = await element.inner_text()
                        if text and len(text.strip()) >= 30:
                            scraped_articles.append({
                                "article_id": idx + 1,
                                "selector": selected_selector,
                                "text": text.strip()
                            })
                    except Exception:
                        continue
            else:
                paragraphs = await page.locator("p").all()
                combined_p = []
                for p_loc in paragraphs:
                    p_text = await p_loc.inner_text()
                    if len(p_text.strip()) > 40:
                        combined_p.append(p_text.strip())
                
                if combined_p:
                    scraped_articles.append({
                        "article_id": 1,
                        "selector": "p_combined",
                        "text": "\n".join(combined_p)
                    })

            await browser.close()

            return {
                "scraped_articles": scraped_articles,
                "timestamp": datetime.now(),
                "metadata": {
                    **metadata,
                    "scrape_success": True,
                    "total_articles_extracted": len(scraped_articles)
                }
            }

    except Exception as e:
        return {
            "scraped_articles": [],
            "metadata": {**metadata, "scrape_error": str(e)},
            "human_review_status": "rejected"
        }