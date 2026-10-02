import os
import re
import asyncio
import subprocess
import edge_tts
from config import FFMPEG_PATH, TEMP_DIR, VOICES

def clean_speech_text(text: str) -> str:
    """Cleans text of markdown, quotes, emojis, and symbols for clean TTS and subtitles."""
    t = re.sub(r"[*_~`#\[\](){}<>|\"]", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t if t else "..."

def get_audio_duration(audio_path: str) -> float:
    """Extracts exact duration in seconds from an audio file using FFmpeg."""
    cmd = [FFMPEG_PATH, "-i", audio_path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    return 4.0

async def generate_speech_async(text: str, voice_id: str, output_path: str, rate: str = "+0%", pitch: str = "+0Hz"):
    """Asynchronously generates speech using Microsoft Edge-TTS."""
    communicate = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def generate_scene_audio(text: str, voice_id: str, output_path: str) -> tuple[float, str]:
    """
    Generates scene audio and returns (duration, cleaned_text)
    so subtitles can use the exact same cleaned text.
    """
    cleaned = clean_speech_text(text)
    asyncio.run(generate_speech_async(cleaned, voice_id, output_path))
    duration = get_audio_duration(output_path)
    return duration, cleaned

def format_srt_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS,mmm string for SRT format."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def generate_scene_srt(text: str, duration: float, output_srt_path: str):
    """
    Splits the exact spoken narration text into timed subtitle chunks.
    Uses proportional speech-length weighting so subtitles appear exactly as words are spoken.
    """
    cleaned = clean_speech_text(text)
    words = cleaned.split()
    if not words:
        words = ["..."]

    # Group into dynamic chunks of 3-4 words for fast viral video rhythm
    chunks = []
    chunk_size = 3 if len(words) <= 12 else 4
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append(chunk)

    total_chars = sum(max(2, len(c)) for c in chunks)
    srt_entries = []
    current_time = 0.0

    for idx, chunk in enumerate(chunks):
        # Time allocated proportionally to chunk character length
        weight = len(chunk) / total_chars
        chunk_dur = max(0.8, duration * weight)
        start_t = current_time
        end_t = min(duration, current_time + chunk_dur)
        current_time = end_t

        srt_entries.append(
            f"{idx + 1}\n{format_srt_time(start_t)} --> {format_srt_time(end_t)}\n{chunk}\n"
        )

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")
