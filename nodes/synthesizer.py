"""
Synthesis Node - Generates Daily Press Review from Classified Articles
Handles batch processing with:
- MERGING: Combines multiple batches into one cohesive report
- ASYNC: Processes batches concurrently (faster)
"""

import json
import logging
import asyncio
from datetime import date
from pathlib import Path
from typing import List, Optional

from ollama import chat, ResponseError
from pydantic import BaseModel, Field, ValidationError

# LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# CONFIGURATION
class PipelineConfig(BaseModel):
    """Stores all configuration values."""
    model_name: str = "qwen2.5:3b-instruct"
    output_dir: Path = Path("data/syntheses")
    max_articles_per_batch: int = 3
    temperature: float = 0.0
    max_concurrent_batches: int = 1  # Limit parallel requests to protect system


# DATA MODELS
class ArticleInput(BaseModel):
    article_id: str
    text: str
    source: str = ""
    language: str = ""


class SynthesizedItem(BaseModel):
    headline: str
    summary: str
    sources: List[str] = Field(default_factory=list)


class SynthesisSection(BaseModel):
    section_title: str
    items: List[SynthesizedItem]


class DailySynthesis(BaseModel):
    date: str
    sections: List[SynthesisSection]


# SYSTEM PROMPT
SYSTEM_PROMPT = """
You are a professional press review writer for Algerian news.
Your job is to read multiple news articles and create a structured daily synthesis.

RULES:
1. Group articles by topic (Politics, Economy, Society, Security, etc.)
2. For each topic, write a summary that captures the key points
3. For each summary, provide a headline and list the sources

OUTPUT FORMAT (JSON):
{
  "date": "2026-09-04",
  "sections": [
    {
      "section_title": "Politics",
      "items": [
        {
          "headline": "New Law Passed",
          "summary": "The parliament passed a new law...",
          "sources": ["Al Jazeera", "Ennahar"]
        }
      ]
    }
  ]
}

Always respond in Arabic. Be concise but comprehensive.
"""


# BATCH PROCESSING (Sync Version - Called by Async)
def build_user_prompt(articles: list[ArticleInput]) -> str:
    """Converts articles into a prompt for the AI."""
    lines = [
        f"ARTICLE ID: {a.article_id}\nLANGUAGE: {a.language}\nSOURCE: {a.source}\nTEXT:\n{a.text}\n"
        for a in articles
    ]
    return f"Create today's Arabic press review from the SAFE articles below.\nDate: {date.today().isoformat()}\n\n{''.join(lines)}"


def synthesize_batch_sync(articles: list[ArticleInput], config: PipelineConfig) -> Optional[DailySynthesis]:
    """
    Synchronous batch synthesis. Used by async functions via asyncio.to_thread().
    
    Why separate? Ollama's chat() is synchronous. We run it in a thread pool.
    """
    if not articles:
        return None
    
    if len(articles) > config.max_articles_per_batch:
        logger.error(f"Batch too large: {len(articles)} > {config.max_articles_per_batch}")
        return None
    
    try:
        user_prompt = build_user_prompt(articles)
        
        response = chat(
            model=config.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            format=DailySynthesis.model_json_schema(),
            options={"temperature": config.temperature},
        )
        
        return DailySynthesis.model_validate_json(response.message.content)
        
    except ResponseError as e:
        logger.error(f"Ollama API failed: {e}")
        return None
    except ValidationError as e:
        logger.error(f"AI returned invalid schema: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None


# ASYNC BATCH PROCESSING (Concurrent)
async def synthesize_batch_async(
    batch: list[ArticleInput], 
    config: PipelineConfig,
    semaphore: asyncio.Semaphore
) -> Optional[DailySynthesis]:
    """
    Asynchronously processes one batch.
    Uses semaphore to limit concurrent requests.
    
    Analogy: The traffic cop at toll booths.
    Only allows max_concurrent_batches cars through at once.
    """
    async with semaphore:
        logger.info(f"🔄 Starting batch of {len(batch)} articles...")
        
        # Run the synchronous chat() in a thread pool
        # This prevents blocking the event loop
        result = await asyncio.to_thread(
            synthesize_batch_sync, 
            batch, 
            config
        )
        
        if result:
            logger.info(f"✅ Batch completed: {len(result.sections)} sections")
        else:
            logger.warning("⚠️ Batch failed")
        
        return result


async def process_all_articles_async(
    articles: list[ArticleInput], 
    config: PipelineConfig
) -> List[DailySynthesis]:
    """
    Splits articles into batches and processes them CONCURRENTLY.
    
    Analogy: Instead of one barista making 4 coffees one by one,
    you have 3 baristas making them all at the same time.
    """
    if not articles:
        return []
    
    total = len(articles)
    batch_size = config.max_articles_per_batch
    
    # Split into batches
    batches = [
        articles[i:i + batch_size] 
        for i in range(0, total, batch_size)
    ]
    
    logger.info(f" Splitting {total} articles into {len(batches)} batches")
    
    # --- SEMAPHORE: Limit concurrent requests ---
    # Prevents overwhelming your system with too many Ollama calls
    semaphore = asyncio.Semaphore(config.max_concurrent_batches)
    
    # --- CREATE ALL TASKS ---
    # All batches start at the same time
    tasks = [
        synthesize_batch_async(batch, config, semaphore) 
        for batch in batches
    ]
    
    # --- RUN CONCURRENTLY ---
    # asyncio.gather() runs all tasks in parallel
    # It waits for ALL to complete before returning
    results = await asyncio.gather(*tasks)
    
    # Filter out None values (failed batches)
    successful_results = [r for r in results if r is not None]
    
    logger.info(f"✅ Completed {len(successful_results)} out of {len(batches)} batches")
    return successful_results


# MERGING FUNCTION (FIX #1: Fragmented Output)
def merge_syntheses(syntheses: list[DailySynthesis], target_date: str) -> DailySynthesis:
    """
    Merges multiple DailySynthesis objects into ONE cohesive report.
    
    Analogy: Instead of printing 3 drafts back-to-back,
    the Chief Editor combines them into one final article.
    
    How it works:
    1. Collects all sections from all syntheses
    2. Groups items by section_title
    3. Returns a single DailySynthesis with merged sections
    """
    merged_sections = {}
    
    for synth in syntheses:
        for section in synth.sections:
            if section.section_title not in merged_sections:
                merged_sections[section.section_title] = []
            
            # Add ALL items from this section to the merged list
            merged_sections[section.section_title].extend(section.items)
    
    # Rebuild the final validated object
    final_sections = [
        SynthesisSection(section_title=title, items=items)
        for title, items in merged_sections.items()
    ]
    
    logger.info(f"🔄 Merged {len(syntheses)} syntheses into {len(final_sections)} sections")
    
    return DailySynthesis(date=target_date, sections=final_sections)


# RENDER & SAVE FUNCTIONS (Unchanged)
def render_markdown(result: DailySynthesis, is_new_file: bool) -> str:
    """Converts DailySynthesis to Markdown format."""
    output = []
    
    if is_new_file:
        output.extend([f"# معرض الصحافة السمعية البصرية — {result.date}", ""])
    
    for section in result.sections:
        output.extend([f"## {section.section_title}", ""])
        for item in section.items:
            output.extend([f"### {item.headline}", item.summary])
            if item.sources:
                output.append(f"- {'، '.join(item.sources)} -")
            output.append("")
    
    return "\n".join(output)


def append_daily_file(result: DailySynthesis, config: PipelineConfig) -> Optional[Path]:
    """Saves a DailySynthesis to a Markdown file."""
    if not result:
        return None
    
    config.output_dir.mkdir(parents=True, exist_ok=True)
    file_path = config.output_dir / f"daily_synthesis_{result.date.replace('-', '_')}.md"
    
    is_new_file = not file_path.exists()
    content = render_markdown(result, is_new_file)
    
    try:
        with file_path.open("a", encoding="utf-8") as f:
            if not is_new_file:
                f.write("\n---\n\n")
            f.write(content)
        
        logger.info(f" Saved synthesis to: {file_path}")
        return file_path
        
    except IOError as e:
        logger.error(f"Failed to write to file {file_path}: {e}")
        return None


# MAIN LOOP (UPDATED WITH MERGE + ASYNC)
async def consume_and_process(
    articles: list[ArticleInput], 
    config: PipelineConfig
):
    """
    Main async loop: Consumes articles, processes batches, merges, saves.
    
    Updated with:
    1. Async batch processing (concurrent)
    2. Merging (one cohesive report)
    3. Single save (no fragmentation)
    """
    logger.info(" Starting queue consumer (async)...")
    logger.info(f" Received {len(articles)} articles.")
    
    # --- Step 1: Process all articles in batches (CONCURRENTLY) ---
    batch_results = await process_all_articles_async(articles, config)
    
    if not batch_results:
        logger.error(" No synthesis results generated.")
        return
    
    logger.info(f" Generated {len(batch_results)} batch syntheses.")
    
    # --- Step 2: Merge into ONE report ---
    logger.info(" Merging batch results into a single daily report...")
    final_synthesis = merge_syntheses(
        batch_results, 
        target_date=date.today().isoformat()
    )
    
    # --- Step 3: Save ONCE ---
    saved_path = append_daily_file(final_synthesis, config)
    
    if saved_path:
        logger.info(f" Final report saved to {saved_path}")
    else:
        logger.error("Failed to save final report")


# SYNC WRAPPER (For easy testing from main.py)
def run_synthesis_pipeline(articles: list[ArticleInput], config: Optional[PipelineConfig] = None):
    """
    Synchronous wrapper for the async pipeline.
    This is what you call from main.py.
    """
    if config is None:
        config = PipelineConfig()
    
    # Run the async function
    asyncio.run(consume_and_process(articles, config))


# TEST HARNESS
if __name__ == "__main__":
    """
    Test the batch processing with sample articles.
    Run: python synthesizer.py
    """
    config = PipelineConfig()
    
    # Create 15 test articles
    test_articles = []
    for i in range(15):
        test_articles.append(
            ArticleInput(
                article_id=f"test_{i:03d}",
                text=f"هذا هو نص المقال رقم {i+1} حول الأخبار الجزائرية. يستمر النص لمدة كافية ليكون واقعيًا...",
                source="النهار تيفي",
                language="ar"
            )
        )
    
    logger.info(f"🧪 Created {len(test_articles)} test articles.")
    
    # Run the pipeline
    run_synthesis_pipeline(test_articles, config)