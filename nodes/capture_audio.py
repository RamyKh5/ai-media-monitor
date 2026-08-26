"""
Audio Capture Module
- Contains both the core FFmpeg streaming helper and the LangGraph node wrapper.
- Uses UUID for unique temp file names to prevent concurrent collision.
"""

import os
import uuid
import logging
import subprocess
import tempfile
from typing import Dict, Any, Optional
from schema_state import AgentState

logger = logging.getLogger(__name__)


def capture_stream_audio(
    stream_url: str,
    output_path: str,
    duration_seconds: int = 30,
    is_youtube: bool = False
) -> bool:
    """
    Core utility: Extracts audio from YouTube or HLS streams using yt-dlp and FFmpeg.
    """
    try:
        audio_url = stream_url

        if is_youtube:
            import yt_dlp
            logger.info(f"Extracting audio stream from YouTube: {stream_url}")
            ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(stream_url, download=False)
                audio_url = info.get('url')
            logger.info("YouTube audio stream extracted successfully")

        # Build FFmpeg command to capture stream chunk
        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_url,
            "-t", str(duration_seconds),
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", "128k",
            output_path
        ]

        logger.info(f"Starting FFmpeg capture for {duration_seconds}s...")
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=duration_seconds + 15
        )

        if process.returncode != 0:
            logger.error(f"FFmpeg failed:\n{process.stderr}")
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        logger.error(f"Error during audio capture: {e}", exc_info=True)
        return False


async def capture_audio_node(state: AgentState) -> dict:
    """
    LangGraph Node: Orchestrates audio capture and stores the path in state metadata.
    """
    metadata = state.get("metadata") or {}
    
    stream_url = metadata.get("stream_url")
    is_youtube = metadata.get("is_youtube", False)
    duration_seconds = metadata.get("duration_seconds", 30)
    channel_name = metadata.get("channel_name", "Unknown TV")

    if not stream_url:
        logger.error("No stream_url provided in metadata")
        return {
            "metadata": {
                **metadata,
                "audio_capture_status": "error",
                "audio_error": "Missing stream_url"
            },
            "reasoning": "Audio capture failed: no stream URL"
        }

    # Generate a unique temporary file path using UUID to prevent concurrency collisions
    unique_id = uuid.uuid4().hex[:8]
    safe_channel_name = channel_name.replace(' ', '_').replace('/', '_')
    temp_file = os.path.join(
        tempfile.gettempdir(),
        f"audio_{safe_channel_name}_{unique_id}.mp3"
    )

    logger.info(f"Starting audio capture for {channel_name} ({duration_seconds}s)")

    success = capture_stream_audio(
        stream_url=stream_url,
        output_path=temp_file,
        duration_seconds=duration_seconds,
        is_youtube=is_youtube
    )

    if not success or not os.path.exists(temp_file):
        logger.error(f"Audio capture failed for {channel_name}")
        return {
            "metadata": {
                **metadata,
                "audio_capture_status": "error",
                "audio_error": "Capture failed or file not created"
            },
            "reasoning": "Audio capture failed"
        }

    file_size = os.path.getsize(temp_file)
    logger.info(f"Audio captured successfully: {temp_file} ({file_size} bytes)")

    return {
        "metadata": {
            **metadata,
            "audio_capture_status": "success",
            "audio_file_path": temp_file,
            "audio_file_size": file_size,
            "audio_duration": duration_seconds,
            "channel_name": channel_name
        },
        "reasoning": f"Captured {duration_seconds}s audio from {channel_name}"
    }