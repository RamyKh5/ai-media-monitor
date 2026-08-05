import subprocess
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_audio_stream_url(url: str) -> Optional[str]:
    """
    Extracts the direct audio stream URL from a YouTube video or live stream.
    Uses yt-dlp to get the best audio stream link.
    
    Works with:
    - YouTube videos (https://youtube.com/watch?v=...)
    - YouTube live streams (https://youtube.com/watch?v=...)
    - YouTube Shorts
    """
    try:
        # yt-dlp command to get the direct audio URL only
        # -g: Get the URL directly (no download)
        # -f bestaudio: Get the best quality audio stream
        cmd = ["yt-dlp", "-g", "-f", "bestaudio/best", url]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {result.stderr}")
            return None
        
        audio_url = result.stdout.strip().split('\n')[0]
        return audio_url if audio_url else None
            
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp timed out")
        return None
    except Exception as e:
        logger.error(f"Error extracting audio URL: {e}")
        return None


def capture_stream_audio(
    stream_url: str, 
    output_path: str = "temp_audio.mp3", 
    duration_seconds: int = 180,
    is_youtube: bool = False
) -> bool:
    """
    Captures a fixed duration of audio from a stream URL using FFmpeg.
    
    Supports:
    - Direct stream URLs (HLS, RTSP, etc.)
    - YouTube videos and live streams (when is_youtube=True)
    
    Parameters:
        stream_url: The URL of the stream or YouTube video
        output_path: Where to save the audio file
        duration_seconds: How many seconds to record (default 180 = 3 minutes)
        is_youtube: Set to True if the URL is a YouTube link
    
    Returns:
        True if successful, False otherwise
    """
    # If it's a YouTube URL, extract the actual audio stream URL first
    actual_stream_url = stream_url
    
    if is_youtube or "youtube.com" in stream_url or "youtu.be" in stream_url:
        logger.info(f"Extracting audio stream from YouTube: {stream_url}")
        actual_stream_url = get_audio_stream_url(stream_url)
        
        if not actual_stream_url:
            logger.error("Failed to extract audio stream from YouTube")
            return False
        
        logger.info(f"YouTube audio stream extracted successfully")
    
    # Remove existing file to avoid conflicts
    if os.path.exists(output_path):
        os.remove(output_path)

    # FFmpeg command to capture audio
    cmd = [
        "ffmpeg",
        "-y",                           # Overwrite output
        "-i", actual_stream_url,        # Input stream
        "-t", str(duration_seconds),    # Duration to record
        "-vn",                          # Video OFF (audio only)
        "-acodec", "libmp3lame",        # Encode to MP3
        output_path
    ]

    try:
        logger.info(f"Starting FFmpeg capture for {duration_seconds}s...")
        
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            timeout=duration_seconds + 30
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr}")
            return False

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"Successfully captured audio to {output_path}")
            return True
        else:
            logger.error("FFmpeg exited, but output file is missing or empty.")
            return False

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg process timed out.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error running FFmpeg: {e}")
        return False