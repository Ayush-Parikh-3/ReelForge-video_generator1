# ReelForge Studio

An automated AI Prompt-to-Video web application that converts text prompts or custom scripts into fully produced, cinematic MP4 videos with scriptwriting, scene distribution, AI neural voiceover, high-resolution visuals, dynamic camera movement, synchronized subtitles, and ambient soundtrack mixing using **FFmpeg** and **100% Free Services**.

---

---

##  Key Features

1. **Smart Scripting & Scene Distribution**:
   - **Enter a Topic**: Generates a progressive, cohesive storyline arc from origin to climax to future without generic filler.
   - **Paste Your Own Script**: Automatically detects multi-sentence stories or explicit scenes (`Scene 1:`, `Scene 2:`) and divides your text evenly across the requested scene count.
   - **Gemini Free API or Instant Storyline**: Use your free Google Gemini API key or rely on the instant, zero-latency local storyline engine.

2. **Neural Voiceover & Word-Accurate Subtitles**:
   - High-fidelity natural voiceovers powered by **Microsoft Edge-TTS** (100% free, 0 API keys required).
   - 12+ voices across English (US/UK/India), Spanish, French, German, and Japanese.
   - Subtitles extracted directly from cleaned spoken audio with speech-length proportional timing burned into the video.
   - Customizable subtitle styling (Viral Yellow, Clean White, Cyber Cyan, Gold).

3. **Multi-Tier Visual Generation**:
   - **Google Gemini Imagen 3**: State-of-the-art AI photorealism when Gemini API key is configured.
   - **Wikimedia Commons**: High-resolution authentic photography matched to scene keywords.
   - **Kinetic Theme Canvas**: Stylized neon gradients and animated geometric frames rendered locally in `<0.01s` as a zero-fail fallback.
   - Aspect ratios supported: **16:9 Landscape** (YouTube/Web) and **9:16 Portrait** (TikTok/Reels/Shorts).

4. **Optimized FFmpeg Video Engine**:
   - Dynamic alternating **Ken Burns camera motion** (Push-in, Pull-out, Horizontal Pan, Diagonal Drift) evaluated at `20 fps`.
   - **Stream-Copy Scene Concat (`-c copy`)**: Concatenates scenes in 0.2s without re-encoding frames.
   - **Pre-generated Ambient Synth Score**: Synthesized concurrently during visuals and clip rendering, then mixed using `-c:v copy`.
   - Native H.264 Baseline + AAC stereo encoding with `playsinline` and `+faststart` for universal playback on iOS Safari, Android, and Desktop browsers.

5. **Two Production Modes**:
   - **⚡ 1-Click Fast Video**: Generates and downloads the complete MP4 video automatically in ~15 seconds.
   - **📝 Storyboard Studio**: Generates and displays each scene card first, allowing you to edit narrations and visual prompts before rendering.

---

##  Quick Start Guide

Local Run (Your PC)
1. Install Python 3.10+ (if not already installed).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch the studio:
   - Double-click `run.bat` or run:
     ```bash
     python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
     ```
4. Open your browser at **`http://localhost:8000`**.

---
---


---

## Free API Configuration (Zero Mandatory Keys)

| Service | Provider | Cost | Setup |
| :--- | :--- | :--- | :--- |
| **Script Generation** | Local Storyline Engine | 100% Free | ❌ **No Key Required** |
| **Advanced Scripting** | Google Gemini Flash | Free Tier | Optional key in "Keys & Config" |
| **Voiceover (TTS)** | Microsoft Edge-TTS | 100% Free | ❌ **No Key Required** |
| **Visuals (Photography)** | Wikimedia Commons | 100% Free | ❌ **No Key Required** |
| **Visuals (AI Imagen 3)** | Google Gemini Imagen 3 | Free Tier | Optional key in "Keys & Config" |
| **Video Assembly** | FFmpeg | Open Source | ❌ **Bundled Automatically** |

---

## 📁 Repository Structure

```
prompt-to-video/
├── config.py            # Global paths, voice registry, styles, dimensions
├── llm_service.py       # User script distributor, topic storylines & Gemini client
├── tts_service.py       # Edge-TTS neural speech synthesis & synchronized SRT generator
├── image_service.py     # Gemini Imagen 3, Wikimedia photo search & kinetic canvas
├── video_service.py     # FFmpeg Ken Burns motion, subtitles, stream-copy concat & audio mix
├── pipeline.py          # Parallel multi-threaded orchestrator & job tracker
├── server.py            # FastAPI backend & static file server
├── live.py              # 1-click local + Cloudflare tunnel launcher
├── share.bat            # 1-click Windows public share launcher
├── run.bat              # 1-click Windows local server launcher
├── requirements.txt     # Python dependencies
├── Dockerfile           # Multi-platform Linux container definition
├── .gitignore           # Git ignore rules for intermediate cache & output
├── static/
│   ├── index.html       # Studio web interface
│   ├── style.css        # Responsive dark UI styling
│   └── app.js           # Frontend interactivity, active job restore & polling
├── output/              # Final rendered MP4 videos & metadata JSON
└── temp/                # Intermediate audio, image, and clip cache
```

---

## 📜 License
MIT License. Free for personal and commercial use.
