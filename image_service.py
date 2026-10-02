import os
import re
import io
import base64
import urllib.parse
import logging
import requests
from PIL import Image, ImageDraw, ImageFont
from config import DIMENSIONS, STYLES

logger = logging.getLogger(__name__)

STYLE_PALETTES = {
    "cinematic": {"bg_top": (10, 16, 26), "bg_bot": (28, 38, 58), "accent": (234, 179, 8), "glow": (202, 138, 4)},
    "cyberpunk": {"bg_top": (13, 6, 28), "bg_bot": (35, 12, 54), "accent": (6, 182, 212), "glow": (236, 72, 153)},
    "anime": {"bg_top": (15, 23, 42), "bg_bot": (30, 41, 59), "accent": (244, 114, 182), "glow": (168, 85, 247)},
    "documentary": {"bg_top": (12, 26, 20), "bg_bot": (20, 45, 36), "accent": (52, 211, 153), "glow": (16, 185, 129)},
    "fantasy": {"bg_top": (24, 12, 38), "bg_bot": (48, 20, 72), "accent": (192, 132, 252), "glow": (147, 51, 234)},
    "vintage": {"bg_top": (38, 28, 20), "bg_bot": (60, 44, 30), "accent": (251, 191, 36), "glow": (217, 119, 6)},
    "minimalist": {"bg_top": (20, 24, 33), "bg_bot": (34, 40, 54), "accent": (96, 165, 250), "glow": (59, 130, 246)}
}

def resize_and_crop(image_path: str, target_w: int, target_h: int):
    """Resizes and center-crops an image to exact target video dimensions."""
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            if im.size == (target_w, target_h):
                return
            im_ratio = im.size[0] / im.size[1]
            target_ratio = target_w / target_h

            if im_ratio > target_ratio:
                new_h = target_h
                new_w = int(target_h * im_ratio)
            else:
                new_w = target_w
                new_h = int(target_w / im_ratio)

            im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            im_cropped = im_resized.crop((left, top, left + target_w, top + target_h))
            im_cropped.save(image_path, quality=94)
    except Exception as e:
        logger.warning(f"Resize failed: {e}")

def create_graphic_canvas(title: str, prompt: str, width: int, height: int, style: str, output_path: str):
    """Renders a stylized graphic frame matching the scene theme."""
    pal = STYLE_PALETTES.get(style, STYLE_PALETTES["cinematic"])
    img = Image.new("RGB", (width, height), pal["bg_top"])
    draw = ImageDraw.Draw(img)

    t_r, t_g, t_b = pal["bg_top"]
    b_r, b_g, b_b = pal["bg_bot"]
    for y in range(height):
        ratio = y / height
        r = int(t_r + ratio * (b_r - t_r))
        g = int(t_g + ratio * (b_g - t_g))
        b = int(t_b + ratio * (b_b - t_b))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    cx, cy = width // 2, height // 2
    for rad in [340, 260, 180, 100]:
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=pal["glow"], width=1)

    draw.rounded_rectangle([cx - 240, cy - 70, cx + 240, cy + 70], radius=16, outline=pal["accent"], width=2)
    clean_p = prompt[:80] + "..." if len(prompt) > 80 else prompt
    draw.text((cx, cy - 15), title.upper(), fill=pal["accent"], anchor="mm")
    draw.text((cx, cy + 20), clean_p, fill=(241, 245, 249), anchor="mm")

    img.save(output_path, quality=92)
    return output_path

def generate_with_gemini_imagen(prompt: str, api_key: str, aspect_ratio: str, output_path: str) -> bool:
    """Generates state-of-the-art AI imagery using Google Imagen 3."""
    if not api_key:
        return False
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        ar = "16:9" if aspect_ratio == "16:9" else "9:16"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": ar}
        }
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            predictions = data.get("predictions", [])
            if predictions and "bytesBase64Encoded" in predictions[0]:
                raw_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                with open(output_path, "wb") as f:
                    f.write(raw_bytes)
                logger.info("Successfully generated AI image via Google Imagen 3!")
                return True
    except Exception as e:
        logger.warning(f"Google Imagen 3 request failed: {e}")
    return False

def search_wikimedia_photo(prompt: str, width: int, height: int, output_path: str) -> bool:
    """Finds high-resolution real matching photography from Wikimedia Commons with strict timeout."""
    try:
        # Extract meaningful subject keywords
        words = re.findall(r'\b[A-Za-z]{3,}\b', prompt)
        stop_words = {'the', 'and', 'with', 'from', 'into', 'shot', 'view', 'scene', 'cinematic', 'high', 'detail', 'photorealistic', 'resolution', 'camera', 'dramatic', 'lighting', 'ultra', 'style'}
        filtered = [w for w in words if w.lower() not in stop_words]
        query = " ".join(filtered[:3]) if filtered else prompt[:30]

        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 4,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": width,
            "format": "json"
        }
        headers = {"User-Agent": "ReelForgeBot/1.0 (contact@reelforge.local)"}
        res = requests.get(url, params=params, headers=headers, timeout=3.0)
        if res.status_code == 200:
            pages = res.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                title = p.get("title", "").lower()
                if title.endswith((".jpg", ".jpeg", ".png")):
                    info = p.get("imageinfo", [{}])[0]
                    thumb = info.get("thumburl") or info.get("url")
                    if thumb:
                        img_res = requests.get(thumb, headers=headers, timeout=3.0)
                        if img_res.status_code == 200 and len(img_res.content) > 5000:
                            with open(output_path, "wb") as f:
                                f.write(img_res.content)
                            resize_and_crop(output_path, width, height)
                            logger.info(f"Matched real photography from Commons: {title}")
                            return True
    except Exception as e:
        logger.warning(f"Wikimedia search warning: {e}")
    return False

def fetch_pollinations_image(prompt: str, width: int, height: int, output_path: str, seed: int = None, key: str = None) -> bool:
    """Attempts Pollinations AI image generation with authenticated API key."""
    if not key:
        return False
    try:
        clean_p = re.sub(r"[^\w\s,-]", "", prompt)[:200]
        encoded = urllib.parse.quote(clean_p)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Authorization": f"Bearer {key}"
        }
        url = f"https://gen.pollinations.ai/image/{encoded}?width={width}&height={height}&seed={seed or 42}"

        resp = requests.get(url, headers=headers, timeout=4.0)
        if resp.status_code == 200 and len(resp.content) > 2000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            resize_and_crop(output_path, width, height)
            return True
    except Exception as e:
        logger.warning(f"Pollinations fetch warning: {e}")
    return False

def generate_scene_image(
    prompt: str,
    aspect_ratio: str = "16:9",
    style: str = "cinematic",
    output_path: str = "scene.jpg",
    seed: int = None,
    image_api_key: str = None,
    api_key: str = None
) -> str:
    """
    Generates or fetches visuals matching the scene narration.
    1. Google Gemini Imagen 3 (if Gemini API key provided)
    2. Pollinations AI (if authenticated key provided)
    3. Wikimedia Commons real photography (strict 3.0s timeout)
    4. Kinetic canvas visual fallback (<0.01s instant)
    """
    dim = DIMENSIONS.get(aspect_ratio, DIMENSIONS["16:9"])
    target_w = dim["width"]
    target_h = dim["height"]

    style_suffix = STYLES.get(style, STYLES["cinematic"])
    enhanced_prompt = f"{prompt}, {style_suffix}"

    # 1. Try Google Gemini Imagen 3 if api_key is available
    if api_key and generate_with_gemini_imagen(enhanced_prompt, api_key, aspect_ratio, output_path):
        resize_and_crop(output_path, target_w, target_h)
        return output_path

    # 2. Try Pollinations AI only if user provided an image API key
    if image_api_key and fetch_pollinations_image(enhanced_prompt, target_w, target_h, output_path, seed=seed, key=image_api_key):
        return output_path

    # 3. Try finding real high-resolution matching photography with 3.0s timeout
    if search_wikimedia_photo(prompt, target_w, target_h, output_path):
        return output_path

    # 4. Fallback to stylized kinetic canvas (<0.01s)
    return create_graphic_canvas("Visual Scene", prompt, target_w, target_h, style, output_path)
