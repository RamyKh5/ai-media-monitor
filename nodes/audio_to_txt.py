"""
Audio Transcription Node (Whisper)
- Singleton pattern: loads model once per process
- Request size limits: prevents huge files from overwhelming the system
- Disk space leak fix: automatically deletes temporary files after transcription
- Standardized output for pipeline integration
"""

import os
import logging
import whisper
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# GLOBAL SINGLETON: Holds the model in memory across node invocations
_WHISPER_MODEL = None

# --- CONFIGURATION: Size Limits ---
MAX_AUDIO_SIZE_MB = 50              # 50MB max file size
MAX_AUDIO_DURATION_SECONDS = 300    # 5 minutes max duration (safety net)
WHISPER_MODEL_SIZE = "base"         # "tiny", "base", "small", "medium", "large"
WHISPER_LANGUAGE = "ar"             # "ar" for Arabic, "en" for English, None for auto-detect


def get_whisper_model(model_size: str = WHISPER_MODEL_SIZE) -> whisper.Whisper:
    """
    Lazy-load the Whisper model only when first needed,
    then cache it globally to prevent reloading.
    """
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        logger.info(f"Loading local Whisper model ({model_size}) into memory...")
        try:
            _WHISPER_MODEL = whisper.load_model(model_size)
            logger.info("Whisper model loaded successfully.")
        except RuntimeError as e:
            # Memory fallback: if GPU fails, try CPU with smaller model
            if "CUDA out of memory" in str(e) and model_size != "tiny":
                logger.warning(f"GPU memory error with '{model_size}', falling back to 'tiny'")
                _WHISPER_MODEL = whisper.load_model("tiny")
                logger.info("Whisper model loaded successfully (fallback: tiny).")
            else:
                logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
                raise RuntimeError(f"Whisper initialization failed: {e}")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
            raise RuntimeError(f"Whisper initialization failed: {e}")
    return _WHISPER_MODEL


def get_audio_duration(file_path: str) -> float:
    """
    Get audio duration in seconds using FFprobe (fallback method).
    If FFprobe fails, returns 0 (unknown).
    """
    import subprocess
    
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def transcribe_audio_file(
    file_path: str,
    channel_name: str = "Unknown TV",
    model_size: str = WHISPER_MODEL_SIZE,
    language: Optional[str] = WHISPER_LANGUAGE,
    auto_delete: bool = True
) -> List[Dict[str, Any]]:
    """
    Takes a local audio file path, runs Whisper transcription,
    and formats the output to match the pipeline's standard schema.

    --- REQUEST SIZE LIMITS (Industry Standard) ---
    1. File size limit: 50MB maximum (prevents memory overload)
    2. Duration limit: 300 seconds (5 minutes) maximum
    
    For live broadcasts: your 15-30s chunks are already well within these limits.

    --- DISK SPACE LEAK FIX ---
    The file is automatically deleted after transcription (success or failure)
    to prevent /tmp from filling up during 24/7 operation.
    
    Args:
        file_path: Path to the audio file
        channel_name: Name of the channel (for metadata)
        model_size: Whisper model size
        language: Language hint ("ar", "en", None for auto-detect)
        auto_delete: Whether to delete the file after transcription (default: True)
    
    Returns:
        List of standardized articles (empty if transcription failed)
    """
    # --- VALIDATION 1: Check file exists ---
    if not file_path or not os.path.exists(file_path):
        logger.error(f"Transcription failed: Audio file path is invalid or missing: {file_path}")
        return []

    # --- VALIDATION 2: Check file size ---
    file_size_bytes = os.path.getsize(file_path)
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    if file_size_mb > MAX_AUDIO_SIZE_MB:
        logger.error(
            f"File too large: {file_size_mb:.2f}MB exceeds limit {MAX_AUDIO_SIZE_MB}MB. "
            f"Skipping transcription for {channel_name}."
        )
        # Clean up even on validation failure
        if auto_delete:
            _cleanup_file(file_path)
        return []

    logger.info(f"File size: {file_size_mb:.2f}MB (limit: {MAX_AUDIO_SIZE_MB}MB)")

    # --- VALIDATION 3: Check duration (if possible) ---
    duration_seconds = get_audio_duration(file_path)
    if duration_seconds > 0:
        logger.info(f"Audio duration: {duration_seconds:.1f}s")
        if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            logger.error(
                f"Audio too long: {duration_seconds:.1f}s exceeds limit {MAX_AUDIO_DURATION_SECONDS}s. "
                f"Skipping transcription for {channel_name}."
            )
            # Clean up even on validation failure
            if auto_delete:
                _cleanup_file(file_path)
            return []
    else:
        logger.warning("Could not determine audio duration (ffprobe not available or file format unknown).")

    # --- VALIDATION PASSED: Proceed with transcription ---
    try:
        model = get_whisper_model(model_size)
        logger.info(f"Starting transcription for file: {file_path} (Channel: {channel_name})")

        # Transcribe with language hint (improves accuracy for Arabic/French/English)
        # fp16=False is required for CPU-only systems
        result = model.transcribe(file_path, language=language, fp16=False)
        transcript_text = result.get("text", "").strip()

        if not transcript_text:
            logger.warning(f"Whisper returned an empty transcript for {channel_name}.")
            return []

        logger.info(f"Successfully transcribed {len(transcript_text)} characters.")

        # --- NORMALIZE TO PIPELINE SCHEMA ---
        standardized_article = {
            "article_id": f"tv_{channel_name}_{abs(hash(transcript_text))}",
            "selector": channel_name,
            "text": transcript_text,
            "source": "tv_broadcast",
            "platform": "television",
            "url": "",
            "date": os.path.getmtime(file_path),
            "likes": 0,
            "comments": 0,
            "shares": 0
        }

        return [standardized_article]

    except Exception as e:
        logger.error(f"Error during Whisper transcription: {e}", exc_info=True)
        return []

    finally:
        # --- THE FIX: Always clean up the temporary file ---
        # This runs whether transcription succeeds or fails.
        # Prevents disk space leaks during 24/7 operation.
        if auto_delete and file_path and os.path.exists(file_path):
            _cleanup_file(file_path)


def _cleanup_file(file_path: str) -> None:
    """
    Safely delete a temporary file.
    Logs success or failure but never raises exceptions.
    """
    try:
        os.remove(file_path)
        logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to delete temp file {file_path}: {e}")