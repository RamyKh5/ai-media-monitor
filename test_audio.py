import sys
import os
import logging
import tempfile

sys.path.append(os.path.dirname(__file__))
from nodes.capture_audio import capture_stream_audio

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # 1. Create a safe, unique temporary file
    # delete=False means the file stays on disk after the 'with' block so Whisper can read it later
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
        safe_output_path = temp_audio.name
    
    print(f"Generated safe temp path: {safe_output_path}")

    # --- TEST 1: YouTube Live ---
    print("\n--- Testing YouTube Live ---")
    success_yt = capture_stream_audio(
        stream_url="https://www.youtube.com/live/bNyUyrR0PHo?si=xDlnKe6r59EW8Aa5",
        output_path=safe_output_path,
        duration_seconds=15, 
        is_youtube=True
    )
    
    # --- TEST 2: HLS TV Stream (Standard TV format) ---
    print("\n--- Testing Raw HLS TV Stream ---")
    # This is a public test HLS stream used by developers
    hls_test_url = "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8"    
    # Notice: is_youtube=False. yt-dlp is bypassed completely.
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_hls:
        safe_hls_path = temp_hls.name

    success_hls = capture_stream_audio(
        stream_url=hls_test_url,
        output_path=safe_hls_path,
        duration_seconds=15,
        is_youtube=False 
    )

    if success_yt:
        print(f"✅ YT Audio saved to: {safe_output_path}")
    if success_hls:
        print(f"✅ HLS Audio saved to: {safe_hls_path}")