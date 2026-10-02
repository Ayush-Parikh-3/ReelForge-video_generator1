import os
import subprocess
import logging
from config import FFMPEG_PATH, DIMENSIONS, OUTPUT_DIR

logger = logging.getLogger(__name__)

def generate_ambient_music(duration: float, output_path: str):
    """Generates a pleasant, calming ambient synth track matching video length."""
    dur_str = f"{max(3.0, duration):.1f}"
    filter_complex = (
        f"anoisesrc=d={dur_str}:c=pink:r=44100:a=0.015,lowpass=f=350[noise];"
        f"sine=f=110:d={dur_str}[n1];"
        f"sine=f=164.81:d={dur_str}[n2];"
        f"sine=f=220:d={dur_str}[n3];"
        f"[n1][n2][n3]amix=inputs=3:dropout_transition=2[syn];"
        f"[syn]volume=0.06[synv];"
        f"[noise][synv]amix=inputs=2:dropout_transition=2,afade=t=in:ss=0:d=1.5,afade=t=out:st={duration-1.5:.1f}:d=1.5[out]"
    )
    cmd = [
        FFMPEG_PATH, "-y",
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", dur_str,
        output_path
    ]
    subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, errors="ignore")

def render_scene_clip(
    image_path: str,
    audio_path: str,
    srt_path: str,
    output_path: str,
    duration: float,
    aspect_ratio: str = "16:9",
    scene_idx: int = 0,
    subtitle_color: str = "yellow"
) -> bool:
    """
    Renders an active cinematic scene:
    High-energy camera motion + Audio + Hardcoded Subtitles.
    """
    dim = DIMENSIONS.get(aspect_ratio, DIMENSIONS["16:9"])
    w = dim["width"]
    h = dim["height"]

    color_map = {
        "yellow": "&H0000FFFF",
        "white": "&H00FFFFFF",
        "cyan": "&H00FFFF00",
        "gold": "&H0033D1FF"
    }
    hex_color = color_map.get(subtitle_color.lower(), "&H0000FFFF")

    if aspect_ratio == "9:16":
        font_size = 25
        margin_v = 120
    else:
        font_size = 22
        margin_v = 38

    # 4 Dynamic alternating camera motions (Noticeable, engaging, video-like!)
    motion_type = scene_idx % 4
    if motion_type == 0:
        # Dramatic Push-In (Zoom in smoothly from 1.0 to 1.30)
        motion = f"zoompan=z='min(zoom+0.0028,1.30)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=20"
    elif motion_type == 1:
        # Dramatic Pull-Out (Starts zoomed at 1.30 and reveals wide to 1.0)
        motion = f"zoompan=z='if(lte(on,1),1.30,max(1.0,zoom-0.0028))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=20"
    elif motion_type == 2:
        # Cinematic Horizontal Pan across the frame
        motion = f"zoompan=z=1.22:x='min(on*2.0,iw-iw/zoom)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=20"
    else:
        # Diagonal Dynamic Drift
        motion = f"zoompan=z='min(zoom+0.0022,1.26)':x='min(on*1.5,iw/2-(iw/zoom/2))':y='min(on*1.0,ih/2-(ih/zoom/2))':d=1:s={w}x{h}:fps=20"

    work_dir = os.path.dirname(os.path.abspath(image_path))
    rel_img = os.path.basename(image_path)
    rel_audio = os.path.basename(audio_path)
    rel_srt = os.path.basename(srt_path)
    rel_out = os.path.basename(output_path)

    sub_font = "DejaVu Sans" if os.name != "nt" else "Arial"
    sub_style = (
        f"FontName={sub_font},FontSize={font_size},Bold=1,"
        f"PrimaryColour={hex_color},OutlineColour=&H00000000,"
        f"BorderStyle=3,Outline=2.5,Shadow=1.5,Alignment=2,MarginV={margin_v}"
    )

    vf = f"{motion},subtitles={rel_srt}:force_style='{sub_style}'"

    cmd = [
        FFMPEG_PATH, "-y",
        "-loop", "1", "-i", rel_img,
        "-i", rel_audio,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "fastdecode",
        "-crf", "28",
        "-r", "20",
        "-threads", "1",
        "-t", f"{duration:.3f}",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "128k",
        "-shortest",
        rel_out
    ]

    logger.info(f"Rendering scene {scene_idx} ({duration:.2f}s) in {work_dir}...")
    res = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, errors="ignore")
    if res.returncode != 0:
        logger.error(f"FFmpeg scene render error: {res.stderr[-400:]}")
        # Fallback without subtitle filter
        fallback_cmd = [
            FFMPEG_PATH, "-y",
            "-loop", "1", "-i", rel_img,
            "-i", rel_audio,
            "-vf", motion,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-crf", "28",
            "-r", "20",
            "-threads", "1",
            "-t", f"{duration:.3f}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            rel_out
        ]
        fb_res = subprocess.run(fallback_cmd, cwd=work_dir, capture_output=True, text=True, errors="ignore")
        return fb_res.returncode == 0

    return True

def assemble_full_video(
    scene_clips: list,
    output_video_path: str,
    total_duration: float,
    add_music: bool = True,
    job_dir: str = None,
    pre_generated_music: str = None
) -> str:
    """
    Concatenates ALL scene clips at lightning speed (<0.3s) using stream copy (-c copy).
    Mixes ambient background music without re-encoding video frames (-c:v copy).
    """
    if not scene_clips:
        raise ValueError("No scene clips provided to assemble")

    if job_dir is None:
        job_dir = os.path.dirname(scene_clips[0])

    # 1. Create concat list
    concat_file = os.path.join(job_dir, "concat_list.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for clip in scene_clips:
            clip_rel = os.path.basename(clip)
            f.write(f"file '{clip_rel}'\n")

    raw_joined = os.path.join(job_dir, "joined_temp.mp4")

    # Ultra-fast stream-copy concat (Takes ~0.2s, 0 quality loss, seamless play)
    concat_cmd = [
        FFMPEG_PATH, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "concat_list.txt",
        "-c", "copy",
        "joined_temp.mp4"
    ]
    logger.info(f"Assembling {len(scene_clips)} scenes into full video with stream copy...")
    c_res = subprocess.run(concat_cmd, cwd=job_dir, capture_output=True, text=True, errors="ignore")
    if c_res.returncode != 0:
        logger.warning(f"Fast copy concat failed: {c_res.stderr[-300:]}. Falling back to ultrafast re-encode...")
        reencode_cmd = [
            FFMPEG_PATH, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", "concat_list.txt",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "joined_temp.mp4"
        ]
        subprocess.run(reencode_cmd, cwd=job_dir, capture_output=True, text=True, errors="ignore")

    # 2. Add background ambient music
    if add_music and total_duration > 1.0:
        bgm_path = pre_generated_music or os.path.join(job_dir, "ambient_bgm.mp3")
        if not os.path.exists(bgm_path):
            generate_ambient_music(total_duration, bgm_path)

        if os.path.exists(bgm_path):
            rel_bgm = os.path.basename(bgm_path)
            mix_cmd = [
                FFMPEG_PATH, "-y",
                "-i", "joined_temp.mp4",
                "-i", rel_bgm,
                "-filter_complex", "[1:a]volume=0.08[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                output_video_path
            ]
            mix_res = subprocess.run(mix_cmd, cwd=job_dir, capture_output=True, text=True, errors="ignore")
            if mix_res.returncode == 0 and os.path.exists(output_video_path):
                return output_video_path

    # If no music or music mix failed, stream copy raw joined to final output
    final_cmd = [
        FFMPEG_PATH, "-y",
        "-i", raw_joined,
        "-c", "copy",
        "-movflags", "+faststart",
        output_video_path
    ]
    subprocess.run(final_cmd, capture_output=True, text=True, errors="ignore")
    return output_video_path
