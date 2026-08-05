"""
OCR Node - Extract text from scanned PDFs

This node:
1. Receives PDF file path from state
2. Converts each PDF page to image
3. OCR each image (Arabic, French, English support)
4. Formats results to match scraper node output
5. Returns updated state

Why consistent formatting?
keyword_filter_node expects "scraped_articles" list.
Whether data comes from web scraper or OCR, keyword_filter shouldn't care.
"""

import os
os.environ["PATH"] += os.pathsep + r"D:\DOWNLOADS\poppler\poppler-26.02.0\Library\bin"
import re
import asyncio
from typing import List, Dict, Any
from datetime import datetime

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import cv2
import numpy as np
from schema_state import AgentState

def verify_tesseract_languages(required_langs=["ara", "fra"]):
    available = pytesseract.get_languages()
    for lang in required_langs:
        if lang not in available:
            raise EnvironmentError(
                f"Tesseract language '{lang}' missing! Available: {available}"
            )

# Call at startup (add this before the main OCR logic)
verify_tesseract_languages(["ara", "fra"])


def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Image preprocessing: improves OCR accuracy
    
    FIX 1: Changed from Otsu to Adaptive Thresholding
    Why? Otsu uses a global threshold across the entire image.
    Scanned journals have dark spine shadows and uneven lighting.
    Otsu would erase the dark regions entirely.
    Adaptive thresholding examines local neighborhoods (11x11 pixels)
    and decides per-region whether a pixel is text or background.
    This preserves text even in shadows.
    """
    # Convert to OpenCV format
    img = np.array(image)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # FIX 1 APPLIED: Adaptive Thresholding (NOT Otsu)
    # Block size 11, constant 2 is standard for 300 DPI text
    # For lower DPI (150-200): use block size 15-21, constant 3-5
    # For higher DPI (600+): use block size 7-9, constant 1-2
    binary = cv2.adaptiveThreshold(
        gray, 
        255, 
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 
        11,  # Block size (pixel neighborhood)
        2    # Constant subtracted from threshold
    )
    
    # Denoise (median filter removes scanner noise)
    denoised = cv2.medianBlur(binary, 3)
    
    return Image.fromarray(denoised)


def ocr_image(image: Image.Image, lang: str = "ara+fra+eng") -> str:
    """
    OCR a single image
    
    FIX 2: Changed from --psm 6 to --psm 3
    Why? --psm 6 assumes a single uniform text block.
    Government journals are almost always printed in TWO COLUMNS.
    --psm 6 reads left-to-right straight across, mixing Column 1 with Column 2.
    --psm 3 auto-detects the columns and reads each one separately.
    
    Alternative PSM values:
    - 3: Auto detect columns (BEST FOR JOURNALS)
    - 4: Assume single column (for books, letters)
    - 6: Single uniform block (for plain text, no columns)
    - 11: Sparse text (for headlines, posters)
    """
    try:
        # Preprocess with adaptive thresholding
        processed = preprocess_image(image)
        
        # FIX 2 APPLIED: --psm 3 for multi-column support
        # --oem 3 uses LSTM neural network (better for Arabic RTL text)
        text = pytesseract.image_to_string(
            processed, 
            lang=lang, 
            config='--psm 3 --oem 3'
        )
        return text.strip()
        
    except pytesseract.TesseractError as e:
        print(f"[OCR Error] {e}")
        return ""
    except Exception as e:
        print(f"[OCR Error] {e}")
        return ""


def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """
    Convert each PDF page to image
    
    Why 300 DPI? Tesseract officially recommends minimum 300 DPI.
    Below 300 DPI, character details are lost, accuracy drops significantly.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    images = convert_from_path(pdf_path, dpi=dpi)
    return images


def extract_articles_from_ocr(text: str, page_num: int) -> List[Dict[str, Any]]:
    """
    Split OCR output text into "articles"
    
    Current strategy: split by blank lines.
    Journals usually have blank lines between articles.
    
    Future optimization options:
    1. Regex patterns to match article titles
    2. Layout analysis (detect columns, blocks)
    3. ML model for semantic segmentation
    """
    if not text:
        return []
    
    # Split by two or more newlines
    blocks = re.split(r'\n\s*\n', text)
    
    articles = []
    for idx, block in enumerate(blocks):
        block = block.strip()
        if len(block) >= 30:  # Minimum 30 chars to count as article
            articles.append({
                "article_id": f"ocr_p{page_num}_a{idx + 1}",
                "selector": f"ocr_page_{page_num}",
                "text": block,
                "source": "ocr"
            })
    
    return articles


async def ocr_node(state: AgentState) -> dict:
    """
    LangGraph node: Execute OCR
    
    FIX 3: Async blocking handled with asyncio.to_thread()
    Why? pdf_to_images() and ocr_image() are synchronous CPU-heavy functions.
    Running them directly inside an async function blocks the entire event loop.
    No other tasks can process until OCR finishes.
    
    asyncio.to_thread() runs the sync function in a background thread pool.
    The event loop yields control and continues processing other tasks.
    When the thread finishes, the result returns to the async function.
    """
    metadata = state.get("metadata", {}) or {}
    pdf_path = metadata.get("file_path")
    
    if not pdf_path:
        return {
            "scraped_articles": [],
            "metadata": {
                **metadata,
                "ocr_status": "error",
                "ocr_error": "No PDF file path provided"
            },
            "human_review_status": "rejected",
            "reasoning": "OCR failed: missing file path"
        }
    
    if not os.path.exists(pdf_path):
        return {
            "scraped_articles": [],
            "metadata": {
                **metadata,
                "ocr_status": "error",
                "ocr_error": f"File not found: {pdf_path}"
            },
            "human_review_status": "rejected",
            "reasoning": f"OCR failed: cannot find {pdf_path}"
        }
    
    try:
        # FIX 3 APPLIED: Offload PDF conversion to background thread
        # Without asyncio.to_thread(), this would block the event loop
        images = await asyncio.to_thread(pdf_to_images, pdf_path, 300)
        
        if not images:
            return {
                "scraped_articles": [],
                "metadata": {
                    **metadata,
                    "ocr_status": "error",
                    "ocr_error": "PDF has no pages or conversion failed"
                },
                "human_review_status": "rejected",
                "reasoning": "OCR failed: PDF empty"
            }
        
        all_articles = []
        total_pages = len(images)
        
        # NOTE: Sequential processing keeps CPU usage stable during testing.
        # If scanning 50+ page documents in production, consider parallelizing:
        # tasks = [asyncio.to_thread(ocr_image, img, "ara+fra+eng") for img in images]
        # results = await asyncio.gather(*tasks)  # Process all pages in parallel
        # Trade-off: Faster but uses more CPU/memory. Sequential is safer for govt docs.
        for page_num, img in enumerate(images, start=1):
            print(f"[OCR] Processing page {page_num}/{total_pages}...")
            
            # FIX 3 APPLIED: Offload OCR to background thread
            # Without asyncio.to_thread(), this would block the event loop
            text = await asyncio.to_thread(ocr_image, img, "ara+fra+eng")
            
            if text:
                # extract_articles_from_ocr is lightweight, but we offload it anyway
                # to keep everything consistent
                page_articles = await asyncio.to_thread(
                    extract_articles_from_ocr, 
                    text, 
                    page_num
                )
                all_articles.extend(page_articles)
                print(f"[OCR] Page {page_num} extracted {len(page_articles)} articles")
            else:
                print(f"[OCR] Page {page_num} no text found")
        
        return {
            "scraped_articles": all_articles,
            "metadata": {
                **metadata,
                "ocr_status": "success" if all_articles else "no_text_found",
                "ocr_pages_processed": total_pages,
                "total_articles_extracted": len(all_articles),
                "source_type": "scanned_journal"
            },
            "reasoning": f"OCR complete: processed {total_pages} pages, extracted {len(all_articles)} articles"
        }
        
    except Exception as e:
        return {
            "scraped_articles": [],
            "metadata": {
                **metadata,
                "ocr_status": "error",
                "ocr_error": str(e)
            },
            "human_review_status": "pending",
            "reasoning": f"OCR exception: {str(e)}"
        }