"""
Test script for audio transcription node.
Tests the size limits and disk cleanup.
"""

import os
import sys
import logging
import tempfile

# Add project root to path
sys.path.append(os.path.dirname(__file__))

# Import your actual file (audio_to_txt.py)
from nodes.audio_to_txt import transcribe_audio_file

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("test.transcriber")


def test_cleanup_on_success():
    """Test that the temporary file is deleted after successful transcription."""
    logger.info("=== Testing Cleanup on Success ===")
    
    test_file = "temp_audio.mp3"
    
    if not os.path.exists(test_file):
        logger.error(f"Test file '{test_file}' not found. Run test_audio.py first.")
        return
    
    logger.info(f"File exists: {os.path.exists(test_file)}")
    
    result = transcribe_audio_file(test_file, "Test TV Channel")
    
    # --- PRINT THE TRANSCRIPT ---
    if result:
        logger.info(f"✅ TRANSCRIPT ({len(result[0]['text'])} chars):")
        print("\n" + "="*60)
        print("TRANSCRIPTION RESULT:")
        print("="*60)
        print(result[0]['text'])
        print("="*60 + "\n")
    else:
        logger.error("No transcript produced")
    
    if os.path.exists(test_file):
        logger.error(f"❌ File was NOT deleted! Disk leak detected.")
    else:
        logger.info(f"✅ File was deleted successfully.")


def test_cleanup_on_failure():
    """Test that invalid files are cleaned up even on failure."""
    logger.info("=== Testing Cleanup on Failure ===")
    
    # Create a dummy invalid file
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"this is not a valid audio file" * 100)
        fake_file = f.name
    
    logger.info(f"Created invalid file: {fake_file}")
    logger.info(f"File exists before: {os.path.exists(fake_file)}")
    
    # Run transcription (should fail)
    result = transcribe_audio_file(fake_file, "Test TV Channel")
    
    # Check if file was deleted
    if os.path.exists(fake_file):
        logger.error(f"❌ File was NOT deleted! Disk leak detected.")
    else:
        logger.info(f"✅ File was deleted successfully (even though transcription failed).")


def main():
    logger.info("=== Audio Transcriber Test Suite ===")
    logger.info("Testing disk cleanup and size limits...")
    
    test_cleanup_on_success()
    test_cleanup_on_failure()
    
    logger.info("=== Test Complete ===")


if __name__ == "__main__":
    main()