import os
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import TEMP_DIR, OUTPUT_DIR
from llm_service import generate_script
from tts_service import generate_scene_audio, generate_scene_srt
from image_service import generate_scene_image
from video_service import render_scene_clip, assemble_full_video, generate_ambient_music

logger = logging.getLogger(__name__)

# In-memory job status store
JOBS = {}

def update_job_status(job_id: str, stage: str, progress: int, message: str, data: dict = None):
    """Updates job progress and logs for frontend polling."""
    if job_id not in JOBS:
        JOBS[job_id] = {
            "id": job_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "logs": [],
            "error": None,
            "completed": False,
            "video_url": None,
            "metadata": {}
        }
    
    j = JOBS[job_id]
    j["stage"] = stage
    j["progress"] = progress
    j["message"] = message
    timestamp = time.strftime("%H:%M:%S")
    j["logs"].append(f"[{timestamp}] {message}")
    if data:
        j["metadata"].update(data)

def run_full_pipeline(
    prompt: str,
    job_id: str,
    scene_count: int = 4,
    aspect_ratio: str = "16:9",
    style: str = "cinematic",
    voice_id: str = "en-US-ChristopherNeural",
    add_music: bool = True,
    subtitle_color: str = "yellow",
    api_key: str = None,
    image_api_key: str = None
):
    """
    Executes the prompt-to-video pipeline with multi-threaded parallel execution
    for rapid 20-35 second turnaround.
    """
    job_dir = os.path.join(TEMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    start_time = time.time()

    try:
        # Step 1: Scripting
        update_job_status(job_id, "scripting", 15, f"Writing {scene_count}-scene cinematic script for '{prompt}'...")
        script_data = generate_script(
            prompt=prompt,
            scene_count=scene_count,
            style=style,
            api_key=api_key
        )
        title = script_data.get("title", prompt.capitalize())
        scenes = script_data.get("scenes", [])
        if not scenes:
            raise ValueError("No scenes could be generated for this prompt")

        num_scenes = len(scenes)
        update_job_status(
            job_id,
            "scripting",
            30,
            f"Script ready: '{title}' ({num_scenes} scenes). Starting parallel generation...",
            {"title": title, "scenes": scenes}
        )

        scene_data = [None] * num_scenes

        # Step 2: Parallel Voiceovers & Subtitles (All scenes at the same time)
        update_job_status(job_id, "voiceover", 45, f"Synthesizing all {num_scenes} neural voiceovers in parallel...")
        def process_audio(idx, scene):
            narr = scene.get("narration", "")
            audio_file = os.path.join(job_dir, f"scene_{idx}.mp3")
            srt_file = os.path.join(job_dir, f"scene_{idx}.srt")
            # Synthesize voice and extract cleaned text
            duration, spoken_text = generate_scene_audio(narr, voice_id, audio_file)
            # Ensure subtitle text matches the spoken audio 100% word-for-word!
            generate_scene_srt(spoken_text, duration, srt_file)
            return idx, audio_file, srt_file, duration, spoken_text

        with ThreadPoolExecutor(max_workers=min(num_scenes, 6)) as pool:
            futures = [pool.submit(process_audio, idx, scene) for idx, scene in enumerate(scenes)]
            for f in as_completed(futures):
                idx, audio_file, srt_file, duration, spoken_text = f.result()
                scene_data[idx] = {
                    "idx": idx,
                    "scene": scenes[idx],
                    "audio_file": audio_file,
                    "srt_file": srt_file,
                    "duration": duration,
                    "spoken_text": spoken_text
                }

        total_duration = sum(s["duration"] for s in scene_data)

        # Pre-generate ambient background music concurrently during steps 3 and 4
        bgm_future = None
        bgm_file = os.path.join(job_dir, "ambient_bgm.mp3")
        if add_music and total_duration > 1.0:
            bgm_pool = ThreadPoolExecutor(max_workers=1)
            bgm_future = bgm_pool.submit(generate_ambient_music, total_duration, bgm_file)

        # Step 3: Parallel Visuals (All scene images at the same time)
        update_job_status(job_id, "visuals", 65, f"Generating {num_scenes} scene visuals in parallel...")
        def process_image(idx, s_info):
            scene = s_info["scene"]
            vis_prompt = scene.get("visual_prompt", prompt)
            img_file = os.path.join(job_dir, f"scene_{idx}.jpg")
            generate_scene_image(
                prompt=vis_prompt,
                aspect_ratio=aspect_ratio,
                style=style,
                output_path=img_file,
                seed=42 + idx * 7,
                image_api_key=image_api_key,
                api_key=api_key
            )
            s_info["img_file"] = img_file
            return idx

        with ThreadPoolExecutor(max_workers=min(num_scenes, 6)) as pool:
            futures = [pool.submit(process_image, idx, s_info) for idx, s_info in enumerate(scene_data)]
            for f in as_completed(futures):
                f.result()

        # Step 4: Parallel Video Scene Rendering (High-speed FFmpeg with ultrafast preset)
        update_job_status(job_id, "rendering", 80, f"Rendering {num_scenes} scene clips with camera motion & subtitles...")
        def process_video_clip(idx, s_info):
            clip_file = os.path.join(job_dir, f"clip_{idx}.mp4")
            render_scene_clip(
                image_path=s_info["img_file"],
                audio_path=s_info["audio_file"],
                srt_path=s_info["srt_file"],
                output_path=clip_file,
                duration=s_info["duration"],
                aspect_ratio=aspect_ratio,
                scene_idx=idx,
                subtitle_color=subtitle_color
            )
            s_info["clip_file"] = clip_file
            return idx

        render_workers = min(len(scene_data), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=render_workers) as pool:
            futures = [pool.submit(process_video_clip, idx, s_info) for idx, s_info in enumerate(scene_data)]
            for f in as_completed(futures):
                f.result()

        # Step 5: Lightning Fast Concatenation & Audio Mix (<2 seconds total!)
        update_job_status(job_id, "assembly", 92, "Assembling final video with audio sync & score...")
        scene_clips = [s["clip_file"] for s in scene_data if os.path.exists(s.get("clip_file", ""))]

        final_video_name = f"{job_id}.mp4"
        final_output_path = os.path.join(OUTPUT_DIR, final_video_name)

        if bgm_future:
            try:
                bgm_future.result(timeout=4.0)
            except Exception as e:
                logger.warning(f"BGM wait warning: {e}")

        assemble_full_video(
            scene_clips=scene_clips,
            output_video_path=final_output_path,
            total_duration=total_duration,
            add_music=add_music,
            job_dir=job_dir,
            pre_generated_music=bgm_file if os.path.exists(bgm_file) else None
        )

        if not os.path.exists(final_output_path):
            raise RuntimeError("Final video assembly produced no output file")

        elapsed = round(time.time() - start_time, 1)

        # Prepare metadata
        processed_scenes = []
        for s in scene_data:
            processed_scenes.append({
                "scene_id": s["idx"] + 1,
                "narration": s["scene"].get("narration", ""),
                "visual_prompt": s["scene"].get("visual_prompt", ""),
                "duration": round(s["duration"], 2),
                "image_file": f"/temp/{job_id}/scene_{s['idx']}.jpg",
                "audio_file": f"/temp/{job_id}/scene_{s['idx']}.mp3"
            })

        meta_path = os.path.join(OUTPUT_DIR, f"{job_id}.json")
        meta_data = {
            "job_id": job_id,
            "title": title,
            "prompt": prompt,
            "duration": round(total_duration, 1),
            "render_time_sec": elapsed,
            "aspect_ratio": aspect_ratio,
            "style": style,
            "voice_id": voice_id,
            "scenes": processed_scenes,
            "video_url": f"/output/{final_video_name}",
            "created_at": time.time()
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)

        j = JOBS[job_id]
        j["completed"] = True
        j["progress"] = 100
        j["stage"] = "done"
        j["message"] = f"Video ready in {elapsed}s! Enjoy your video."
        j["video_url"] = f"/output/{final_video_name}"
        j["metadata"] = meta_data
        j["logs"].append(f"[{time.strftime('%H:%M:%S')}] Render finished in {elapsed}s! Output: {final_video_name}")

    except Exception as e:
        logger.exception("Pipeline execution failed")
        if job_id in JOBS:
            j = JOBS[job_id]
            j["completed"] = True
            j["error"] = str(e)
            j["stage"] = "error"
            j["message"] = f"Failed: {str(e)}"
            j["logs"].append(f"[{time.strftime('%H:%M:%S')}] ERROR: {str(e)}")
