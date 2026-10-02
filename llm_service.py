import os
import re
import json
import random
import logging
import requests
from config import STYLES

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a master viral video producer and cinematic visual director.
Given a topic, you MUST create an engaging short video script divided into distinct scenes.

CRITICAL INSTRUCTIONS:
1. You MUST generate EXACTLY the number of scenes requested.
2. For each scene:
   - "scene_id": integer (1, 2, 3, etc.)
   - "narration": Punchy, gripping spoken narration (15-25 words, ~4-6 seconds).
   - "visual_prompt": A highly specific visual description that MATCHES THE NARRATION EXACTLY. Describe the physical subject, camera angle, action, lighting, environment, and atmosphere so an AI image generator produces the perfect visual for this exact moment. Avoid vague words; describe visible objects, colors, and camera framing.

Return ONLY valid JSON matching this schema:
{
  "title": "Compelling Video Title",
  "scenes": [
    {
      "scene_id": 1,
      "narration": "First scene narration...",
      "visual_prompt": "Specific visual description matching the first scene..."
    }
  ]
}
Do NOT include any commentary outside the JSON block.
"""

def clean_json_response(raw_text: str) -> dict:
    """Extract and parse JSON from LLM response text, with regex rescue if needed."""
    text = raw_text.strip()
    
    # Try finding markdown code block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end+1]
            
    # Fix potential trailing commas
    text_clean = re.sub(r",\s*([\]}])", r"\1", text)
    
    try:
        parsed = json.loads(text_clean)
        for s in parsed.get("scenes", []):
            s["subtitle_text"] = s.get("narration", "")
        return parsed
    except Exception:
        pass

    # Regex extraction fallback: find all scene blocks
    title_m = re.search(r'"title"\s*:\s*"([^"]+)"', text)
    title = title_m.group(1) if title_m else "Untitled Story"
    
    # Extract scenes individually
    scene_pattern = re.compile(
        r'\{\s*"scene_id"\s*:\s*(\d+)[\s\S]*?"narration"\s*:\s*"([^"]+)"[\s\S]*?"visual_prompt"\s*:\s*"([^"]+)"(?:[\s\S]*?"subtitle_text"\s*:\s*"([^"]*)")?[\s\S]*?\}',
        re.DOTALL
    )
    scenes = []
    for m in scene_pattern.finditer(text):
        s_id = int(m.group(1))
        narr = m.group(2).replace('\\"', '"')
        vis = m.group(3).replace('\\"', '"')
        sub = m.group(4).replace('\\"', '"') if m.group(4) else narr
        scenes.append({
            "scene_id": s_id,
            "narration": narr,
            "visual_prompt": vis,
            "subtitle_text": sub
        })
        
    if scenes:
        return {"title": title, "scenes": scenes}
        
    raise ValueError(f"Could not parse valid scenes from LLM response")

def generate_script_gemini(prompt: str, scene_count: int, style: str, api_key: str) -> dict:
    """Generate script using Google Gemini Free API."""
    style_desc = STYLES.get(style, STYLES["cinematic"])
    user_msg = f"""Topic/Prompt: "{prompt}"
REQUIRED SCENE COUNT: EXACTLY {scene_count} scenes (Numbered 1 to {scene_count}).
Visual Style: {style} ({style_desc})
Write a gripping script with EXACTLY {scene_count} scenes. Make visual prompts match each scene's narration precisely. Return valid JSON only."""

    models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash"]
    last_err = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_msg}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "response_mime_type": "application/json"
            }
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return clean_json_response(text)
            else:
                last_err = f"Gemini error {resp.status_code}: {resp.text}"
        except Exception as e:
            last_err = str(e)
            continue
            
    raise RuntimeError(f"Gemini API request failed: {last_err}")

def generate_script_pollinations(prompt: str, scene_count: int, style: str, timeout: float = 2.5) -> dict:
    """Generate script using Free Pollinations Text API with strict timeout."""
    style_desc = STYLES.get(style, STYLES["cinematic"])
    user_msg = f"""Topic/Prompt: "{prompt}"
MANDATORY: You MUST generate EXACTLY {scene_count} distinct scenes, numbered 1 to {scene_count}.
Visual Style: {style} ({style_desc})
Ensure each visual_prompt vividly and specifically depicts the exact event happening in that scene's narration.
Return valid JSON only."""

    url = "https://text.pollinations.ai/"
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        "jsonMode": True,
        "seed": random.randint(100, 99999)
    }
    
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code == 200:
        return clean_json_response(resp.text)
    raise RuntimeError(f"Pollinations Text API error {resp.status_code}: {resp.text}")

def extract_script_segments(text: str) -> list:
    """Detects if user provided a multi-scene or multi-sentence script and extracts segments."""
    raw = text.strip()

    # 1. Explicit scene markers (e.g. "Scene 1:", "Scene 1 -", "1.", "1)", "[Scene 1]")
    marker_pattern = re.compile(r'(?:^|\n)\s*(?:Scene\s*\d+[:\-.]?|\d+[\.\)]\s*|\[Scene\s*\d+\])\s*', re.IGNORECASE)
    parts = marker_pattern.split(raw)
    cleaned_parts = [re.sub(r'^(?:Scene\s*\d+[:\-.]?|\d+[\.\)]\s*)', '', p).strip() for p in parts if p.strip()]
    if len(cleaned_parts) >= 2:
        return cleaned_parts

    # 2. Newline-separated lines (if user wrote line by line)
    lines = [l.strip() for l in raw.splitlines() if len(l.strip()) > 8]
    if len(lines) >= 2:
        return lines

    # 3. Multiple sentences separated by punctuation (. ! ?)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw) if len(s.strip()) > 8]
    if len(sentences) >= 2:
        return sentences

    return []

def distribute_user_script(segments: list, scene_count: int, style: str) -> dict:
    """
    Evenly distributes user-provided script segments across the requested scene count.
    Ensures Scene 1 gets Part 1, Scene 2 gets Part 2, etc., with tailored visual prompts.
    """
    style_desc = STYLES.get(style, STYLES["cinematic"])
    num_seg = len(segments)

    # Derive clean title from first segment
    title = segments[0][:40].strip()
    if len(title) > 37:
        title = title[:34] + "..."

    allocated = [[] for _ in range(scene_count)]
    for i, seg in enumerate(segments):
        target_idx = min(i * scene_count // num_seg, scene_count - 1)
        allocated[target_idx].append(seg)

    scenes = []
    for i in range(scene_count):
        if allocated[i]:
            narr = " ".join(allocated[i]).strip()
        else:
            narr = f"Continuing this remarkable story, the journey unfolds with greater intensity."

        # Extract meaningful visual keywords from this specific scene's narration
        vis_words = re.findall(r'\b[A-Za-z]{3,}\b', narr)
        stop_words = {'the', 'and', 'with', 'from', 'into', 'that', 'this', 'have', 'been', 'were', 'will', 'they', 'their', 'there'}
        meaningful = [w for w in vis_words if w.lower() not in stop_words]
        focus = " ".join(meaningful[:6]) if meaningful else narr[:40]

        vis_prompt = f"A cinematic scene vividly showing {focus}, dramatic lighting, atmospheric depth, 8k resolution, {style_desc}"

        scenes.append({
            "scene_id": i + 1,
            "narration": narr,
            "visual_prompt": vis_prompt,
            "subtitle_text": narr
        })

    return {"title": title, "scenes": scenes}

def generate_topic_storyline(topic: str, scene_count: int, style: str) -> dict:
    """
    Generates a cohesive, progressive multi-scene storyline for a given topic.
    EVERY single scene explores a distinct chapter of that exact topic without generic filler.
    """
    style_desc = STYLES.get(style, STYLES["cinematic"])
    title = topic.strip().capitalize()
    if len(title) > 40:
        title = title[:37] + "..."

    clean_topic = re.sub(r'^(the|a|an)\s+', '', topic.strip(), flags=re.IGNORECASE).strip()
    if len(clean_topic) > 40:
        clean_topic = clean_topic[:37] + "..."

    # Cohesive multi-scene narrative where every scene advances the subject
    story_arc = [
        {
            "narration": f"The story of {clean_topic} begins with an extraordinary vision that reshaped our perspective forever.",
            "visual": f"A dramatic establishing cinematic shot introducing {clean_topic}, epic scale, mysterious atmosphere, volumetric lighting"
        },
        {
            "narration": f"At the heart of {clean_topic} lies a powerful force driven by innovation, courage, and relentless momentum.",
            "visual": f"A dynamic close-up scene capturing {clean_topic} actively in motion, intricate details, glowing energy, cinematic lighting"
        },
        {
            "narration": f"A pivotal turning point propelled {clean_topic} to historic heights, overcoming fierce challenges along the way.",
            "visual": f"A dramatic cinematic panorama showing the monumental impact of {clean_topic}, high contrast, intense atmosphere"
        },
        {
            "narration": f"Today, the extraordinary power and influence of {clean_topic} can be witnessed across the entire world.",
            "visual": f"A wide angle breathtaking view of {clean_topic}, stunning cinematic composition, vibrant colors, photorealistic"
        },
        {
            "narration": f"Yet beneath what we see, new discoveries about {clean_topic} continue to reveal deeper secrets and complexities.",
            "visual": f"A cinematic macro detailed shot exploring the inner depth of {clean_topic}, rich texture, shallow depth of field"
        },
        {
            "narration": f"As we look to the horizon, the future of {clean_topic} promises to revolutionize tomorrow in ways we are only beginning to imagine.",
            "visual": f"An inspiring futuristic landscape inspired by {clean_topic}, golden sunrise, awe-inspiring scale, 8k resolution"
        },
        {
            "narration": f"From humble beginnings to global prominence, {clean_topic} stands as a testament to the pursuit of greatness.",
            "visual": f"An expansive aerial view celebrating {clean_topic}, cinematic lens flare, uplifting warm lighting"
        },
        {
            "narration": f"The legacy of {clean_topic} will endure for generations, constantly inspiring what is possible.",
            "visual": f"An iconic closing hero shot symbolizing {clean_topic}, dramatic backlight, unforgettable composition"
        }
    ]

    scenes = []
    for i in range(scene_count):
        template = story_arc[i % len(story_arc)]
        scenes.append({
            "scene_id": i + 1,
            "narration": template["narration"],
            "visual_prompt": f"{template['visual']}, {style_desc}",
            "subtitle_text": template["narration"]
        })

    return {"title": title, "scenes": scenes}

def ensure_exact_scene_count(script_data: dict, target_count: int, prompt: str, style: str) -> dict:
    """Guarantees that the returned script contains EXACTLY target_count scenes."""
    scenes = script_data.get("scenes", [])
    title = script_data.get("title", prompt.capitalize())

    if len(scenes) >= target_count:
        script_data["scenes"] = scenes[:target_count]
        for idx, s in enumerate(script_data["scenes"]):
            s["scene_id"] = idx + 1
        return script_data

    # If LLM returned fewer scenes, pad with context-aware scenes
    needed = target_count - len(scenes)
    fallback_data = generate_topic_storyline(prompt, target_count, style)
    fallback_scenes = fallback_data["scenes"]

    for i in range(len(scenes), target_count):
        scenes.append(fallback_scenes[i])

    for idx, s in enumerate(scenes):
        s["scene_id"] = idx + 1

    script_data["scenes"] = scenes
    return script_data

def generate_script(prompt: str, scene_count: int = 4, style: str = "cinematic", api_key: str = None) -> dict:
    """
    Main entry point for script generation.
    1. If user provided a script (multiple sentences/scenes), distributes them cleanly across each scene.
    2. If user provided an API key and topic, uses Gemini Flash.
    3. If user provided a topic without API key, uses the dynamic topic storyline generator.
    """
    scene_count = max(2, min(scene_count, 8))

    # Check if user entered their own multi-sentence or multi-scene script
    segments = extract_script_segments(prompt)
    if segments and len(segments) >= 2:
        logger.info(f"User provided multi-part script ({len(segments)} segments). Distributing across {scene_count} scenes...")
        return distribute_user_script(segments, scene_count, style)

    result = None

    # If user has Gemini API Key
    if api_key and api_key.strip():
        try:
            logger.info("Attempting script generation with user Gemini API Key...")
            result = generate_script_gemini(prompt, scene_count, style, api_key.strip())
        except Exception as e:
            logger.warning(f"Gemini API failed: {e}. Falling back to topic storyline...")

    if not result:
        try:
            logger.info("Attempting fast script generation with Pollinations Text API...")
            result = generate_script_pollinations(prompt, scene_count, style, timeout=2.5)
        except Exception as e:
            logger.warning(f"Pollinations text API skipped/failed: {e}. Using topic storyline...")

    if not result or not result.get("scenes"):
        result = generate_topic_storyline(prompt, scene_count, style)

    # Strictly guarantee exact scene count
    return ensure_exact_scene_count(result, scene_count, prompt, style)
