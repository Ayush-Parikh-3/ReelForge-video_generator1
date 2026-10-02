import os
import glob
import json
import uuid
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, BackgroundTasks, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from config import (
    STATIC_DIR, OUTPUT_DIR, TEMP_DIR, FFMPEG_PATH,
    VOICES, STYLES, DIMENSIONS
)
from pipeline import JOBS, update_job_status, run_full_pipeline
from llm_service import generate_script
from tts_service import generate_scene_audio, generate_scene_srt
from image_service import generate_scene_image
from video_service import render_scene_clip, assemble_full_video, generate_ambient_music

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ReelForge Studio", version="1.0.0")

# Enable CORS for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=3)

# Serve static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/temp", StaticFiles(directory=TEMP_DIR), name="temp")

# Pydantic Request Models
class FullVideoRequest(BaseModel):
    prompt: str
    scene_count: Optional[int] = 4
    aspect_ratio: Optional[str] = "16:9"
    style: Optional[str] = "cinematic"
    voice_id: Optional[str] = "en-US-ChristopherNeural"
    add_music: Optional[bool] = True
    subtitle_color: Optional[str] = "yellow"
    api_key: Optional[str] = None
    image_api_key: Optional[str] = None

class ScriptRequest(BaseModel):
    prompt: str
    scene_count: Optional[int] = 4
    style: Optional[str] = "cinematic"
    api_key: Optional[str] = None

class SceneItem(BaseModel):
    scene_id: int
    narration: str
    visual_prompt: str
    subtitle_text: Optional[str] = None

class CustomRenderRequest(BaseModel):
    title: str
    scenes: List[SceneItem]
    aspect_ratio: Optional[str] = "16:9"
    style: Optional[str] = "cinematic"
    voice_id: Optional[str] = "en-US-ChristopherNeural"
    add_music: Optional[bool] = True
    subtitle_color: Optional[str] = "yellow"

class VoicePreviewRequest(BaseModel):
    voice_id: str
    text: Optional[str] = "Welcome to the AI video generator. I am your neural voice."

@app.get("/")
def get_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "AI Prompt to Video Studio Backend is running!"}

@app.get("/api/status")
def get_system_status():
    ffmpeg_ready = os.path.exists(FFMPEG_PATH) or shutil_which_test()
    return {
        "status": "ready",
        "ffmpeg": {
            "path": FFMPEG_PATH,
            "ready": ffmpeg_ready
        },
        "voices": VOICES,
        "styles": list(STYLES.keys()),
        "aspect_ratios": DIMENSIONS
    }

def shutil_which_test():
    import shutil
    return shutil.which("ffmpeg") is not None

@app.post("/api/generate-full-video")
def create_full_video(req: FullVideoRequest, background_tasks: BackgroundTasks):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    update_job_status(job_id, "queued", 0, f"Video job queued for '{req.prompt}'")

    background_tasks.add_task(
        run_full_pipeline,
        prompt=req.prompt.strip(),
        job_id=job_id,
        scene_count=req.scene_count or 4,
        aspect_ratio=req.aspect_ratio or "16:9",
        style=req.style or "cinematic",
        voice_id=req.voice_id or "en-US-ChristopherNeural",
        add_music=req.add_music if req.add_music is not None else True,
        subtitle_color=req.subtitle_color or "yellow",
        api_key=req.api_key,
        image_api_key=req.image_api_key
    )

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/job/{job_id}")
def get_job_progress(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]

@app.post("/api/generate-script-only")
def create_script_only(req: ScriptRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    try:
        data = generate_script(
            prompt=req.prompt.strip(),
            scene_count=req.scene_count or 4,
            style=req.style or "cinematic",
            api_key=req.api_key
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/render-custom-scenes")
def render_custom_scenes(req: CustomRenderRequest, background_tasks: BackgroundTasks):
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    update_job_status(job_id, "queued", 0, f"Custom video rendering queued for '{req.title}'")

    def run_custom():
        job_dir = os.path.join(TEMP_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        try:
            scenes = req.scenes
            num_scenes = len(scenes)
            scene_data = [None] * num_scenes

            # Step 1: Parallel Voiceovers
            update_job_status(job_id, "voiceover", 25, f"Synthesizing {num_scenes} voiceovers in parallel...")
            def process_audio(idx, scene):
                narr = scene.narration
                audio_file = os.path.join(job_dir, f"scene_{idx}.mp3")
                srt_file = os.path.join(job_dir, f"scene_{idx}.srt")
                duration, spoken_text = generate_scene_audio(narr, req.voice_id, audio_file)
                generate_scene_srt(spoken_text, duration, srt_file)
                return idx, audio_file, srt_file, duration, spoken_text

            with ThreadPoolExecutor(max_workers=min(num_scenes, 6)) as pool:
                futures = [pool.submit(process_audio, idx, scene) for idx, scene in enumerate(scenes)]
                for f in futures:
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

            # Pre-generate ambient background music concurrently
            bgm_future = None
            bgm_file = os.path.join(job_dir, "ambient_bgm.mp3")
            if req.add_music and total_duration > 1.0:
                bgm_pool = ThreadPoolExecutor(max_workers=1)
                bgm_future = bgm_pool.submit(generate_ambient_music, total_duration, bgm_file)

            # Step 2: Parallel Visuals
            update_job_status(job_id, "visuals", 55, f"Generating {num_scenes} visuals in parallel...")
            def process_image(idx, s_info):
                vis_prompt = s_info["scene"].visual_prompt
                img_file = os.path.join(job_dir, f"scene_{idx}.jpg")
                generate_scene_image(
                    prompt=vis_prompt,
                    aspect_ratio=req.aspect_ratio,
                    style=req.style,
                    output_path=img_file,
                    seed=100 + idx * 5
                )
                s_info["img_file"] = img_file
                return idx

            with ThreadPoolExecutor(max_workers=min(num_scenes, 6)) as pool:
                futures = [pool.submit(process_image, idx, s_info) for idx, s_info in enumerate(scene_data)]
                for f in futures:
                    f.result()

            # Step 3: Parallel Video Scene Rendering
            update_job_status(job_id, "rendering", 75, f"Rendering {num_scenes} scene clips in parallel...")
            def process_video_clip(idx, s_info):
                clip_file = os.path.join(job_dir, f"clip_{idx}.mp4")
                render_scene_clip(
                    image_path=s_info["img_file"],
                    audio_path=s_info["audio_file"],
                    srt_path=s_info["srt_file"],
                    output_path=clip_file,
                    duration=s_info["duration"],
                    aspect_ratio=req.aspect_ratio,
                    scene_idx=idx,
                    subtitle_color=req.subtitle_color
                )
                s_info["clip_file"] = clip_file
                return idx

            render_workers = min(len(scene_data), os.cpu_count() or 4)
            with ThreadPoolExecutor(max_workers=render_workers) as pool:
                futures = [pool.submit(process_video_clip, idx, s_info) for idx, s_info in enumerate(scene_data)]
                for f in futures:
                    f.result()

            # Step 4: Lightning Assembly
            update_job_status(job_id, "assembly", 92, "Assembling final video...")
            scene_clips = [s["clip_file"] for s in scene_data if os.path.exists(s.get("clip_file", ""))]
            final_video_name = f"{job_id}.mp4"
            final_output_path = os.path.join(OUTPUT_DIR, final_video_name)

            if bgm_future:
                try:
                    bgm_future.result(timeout=4.0)
                except Exception:
                    pass

            assemble_full_video(
                scene_clips=scene_clips,
                output_video_path=final_output_path,
                total_duration=total_duration,
                add_music=req.add_music,
                job_dir=job_dir,
                pre_generated_music=bgm_file if os.path.exists(bgm_file) else None
            )

            processed_scenes = []
            for s in scene_data:
                processed_scenes.append({
                    "scene_id": s["idx"] + 1,
                    "narration": s["scene"].narration,
                    "visual_prompt": s["scene"].visual_prompt,
                    "duration": round(s["duration"], 2),
                    "image_file": f"/temp/{job_id}/scene_{s['idx']}.jpg"
                })

            meta_data = {
                "job_id": job_id,
                "title": req.title,
                "duration": round(total_duration, 1),
                "aspect_ratio": req.aspect_ratio,
                "scenes": processed_scenes,
                "video_url": f"/output/{final_video_name}"
            }
            with open(os.path.join(OUTPUT_DIR, f"{job_id}.json"), "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)

            j = JOBS[job_id]
            j["completed"] = True
            j["progress"] = 100
            j["stage"] = "done"
            j["message"] = "Video created successfully!"
            j["video_url"] = f"/output/{final_video_name}"
            j["metadata"] = meta_data
        except Exception as e:
            logger.exception("Custom render failed")
            if job_id in JOBS:
                j = JOBS[job_id]
                j["completed"] = True
                j["error"] = str(e)
                j["stage"] = "error"
                j["message"] = str(e)

    background_tasks.add_task(run_custom)
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/preview-voice")
def preview_voice(req: VoicePreviewRequest):
    """Generates a short voice preview audio clip."""
    preview_name = f"preview_{uuid.uuid4().hex[:6]}.mp3"
    preview_path = os.path.join(TEMP_DIR, preview_name)
    try:
        generate_scene_audio(req.text, req.voice_id, preview_path)
        return {"audio_url": f"/temp/{preview_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_video_history():
    """Lists previously generated videos from output folder."""
    history = []
    meta_files = glob.glob(os.path.join(OUTPUT_DIR, "*.json"))
    # Sort newest first
    meta_files.sort(key=os.path.getmtime, reverse=True)
    for mf in meta_files[:15]:
        try:
            with open(mf, "r", encoding="utf-8") as f:
                history.append(json.load(f))
        except Exception:
            pass
    return {"history": history}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "="*60)
    print(f"  REELFORGE STUDIO RUNNING ON PORT {port}")
    print(f"  Access Web UI at: http://localhost:{port}")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
