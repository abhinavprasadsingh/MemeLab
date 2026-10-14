import os, io, json, random, re, time, uuid, ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image, ImageDraw, ImageFont, ImageOps
from ddgs import DDGS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "static" / "generated"
OUT.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=64 * 1024)
# Render sits behind one trusted reverse proxy; use the visitor IP for rate limits.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
    headers_enabled=True,
)

@app.errorhandler(429)
def rate_limit_exceeded(_error):
    return jsonify(error="Too many meme requests. Please wait a minute and try again."), 429

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
STYLES = {
    "Aura": "cool, effortlessly confident, internet-native, a little absurd",
    "Classic": "timeless relatable meme humour, short and instantly readable",
    "Savage": "sharp roast energy, witty but not cruel or hateful",
    "Brainrot": "chaotic absurdist Gen Z slang, surreal and intentionally unhinged",
    "Wholesome": "sweet, warm, uplifting and funny",
    "Relatable": "painfully relatable everyday life, student and social situations",
    "Dramatic": "over-the-top cinematic melodrama about a tiny problem",
    "Dark Humour": "dry, dark, clever humour without targeting protected groups or encouraging harm",
    "NPC Mode": "deadpan repetitive internet humour and oddly specific reactions"
}

def ask_groq(situation, style, variation=None):
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing Groq API key. Add GROQ_API_KEY in Render Environment.")

    system = """You are an elite meme writer with the timing of a great stand-up comic and the instincts of a chronically-online group chat.
Your job is not to write a merely relevant caption: make the user actually laugh.
FIRST, silently identify the funniest specific detail, contradiction, awkward consequence, irrational reaction, or painfully true part of the situation. Build the joke around that detail.
JOKE QUALITY RULES:
- Make TOP a clear setup and BOTTOM a real punchline, not two versions of the same sentence.
- Prefer a surprising, specific payoff over generic relatability. Use misdirection, overreaction, irony, absurdly precise details, or a sharp comparison when it fits.
- Sound like a funny human friend, not a motivational quote or an AI trying to sound young.
- Use natural, concise language. Usually 3–8 words per caption; shorter is often funnier.
- Gen Z slang is optional seasoning, never the joke itself. Avoid forced slang, stale catchphrases, and generic filler.
- Avoid tired defaults such as "this was not part of the plan", "my life is a joke", "it's giving", "bro really said", "nobody:", or random "POV:" unless the user's exact context makes it genuinely funny.
- Don't explain the joke. No hashtags, emojis in captions, moral lessons, or extra setup.
- One-word prompts: infer the likely everyday meaning and find a specific comic angle. Full-sentence prompts: preserve the exact details and emotional stakes.
- Be playful and sharp, not cruel. No hateful jokes targeting protected groups.
The IMAGE line must describe a visual that makes THIS joke funnier: a recognizable reaction, specific scene, or visual contrast. Never pick a random animal, generic stock photo, or unrelated meme.
Return exactly three plain lines:
TOP: ...
BOTTOM: ...
IMAGE: ...
No explanations or markdown."""
    angles = [
        "Use an unexpected but believable everyday reaction.",
        "Use a relatable inner-thought people usually do not say out loud.",
        "Use a tiny overreaction to the exact situation.",
        "Use a clever expectation-versus-reality twist.",
        "Use awkward social energy, but only if it fits the context.",
        "Use a short, savage-but-friendly observation.",
        "Use a specific 'this is so me' moment.",
        "Use a funny consequence that naturally follows from the situation.",
        "Use a playful Gen Z group-chat style punchline.",
        "Use a simple, surprising comparison that is immediately obvious."
    ]
    angle = variation or random.choice(angles)
    nonce = uuid.uuid4().hex[:8]
    user = f"""Write a meme people would genuinely send to a friend because the punchline is too accurate:
USER'S SITUATION: {situation}
CHOSEN HUMOUR STYLE: {style} — {STYLES.get(style, STYLES['Relatable'])}
CREATIVE ANGLE: {angle}
UNIQUE GENERATION ID: {nonce}

Before answering, silently brainstorm three different punchlines and choose the funniest, most specific one. Do not output the brainstorm.
Make TOP the setup and BOTTOM the unexpected payoff. The bottom caption must add a new comic idea, not repeat or summarize the top. Use concrete details from the situation wherever possible. Aim for "I hate how accurate this is" humour, sharp irony, or a ridiculous but logical escalation. Keep both lines punchy and readable. Don't force slang. Avoid clichés and stock meme templates. Each generation should explore a genuinely different joke, not just swap a few words. The IMAGE must visually reinforce the punchline and stay on topic.
Return only the TOP, BOTTOM, and IMAGE lines in the required format."""

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": 1.0,
        "max_tokens": 220,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}]
    }
    # Bound provider latency; retry only when the provider rejects the request format.
    response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=(4, 22))
    if response.status_code == 400:
        payload["messages"][0]["content"] = (
            "Return three plain text lines labelled TOP:, BOTTOM:, and IMAGE:. "
            "Make captions and the visual phrase specific to the user's situation. No JSON."
        )
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=(4, 18))
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"Groq API error ({response.status_code}): {str(detail)[:220]}")

    try:
        content = str(response.json()["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        content = ""

    top_match = re.search(r"(?im)^\s*TOP\s*:\s*(.+)$", content)
    bottom_match = re.search(r"(?im)^\s*BOTTOM\s*:\s*(.+)$", content)
    image_match = re.search(r"(?im)^\s*IMAGE\s*:\s*(.+)$", content)
    top = top_match.group(1).strip().strip('"') if top_match else ""
    bottom = bottom_match.group(1).strip().strip('"') if bottom_match else ""
    image_query = image_match.group(1).strip().strip('"') if image_match else ""

    if not top or not bottom:
        try:
            data = json.loads(content)
            top = str(data.get("top", "")).strip()
            bottom = str(data.get("bottom", "")).strip()
            image_query = str(data.get("image_query") or data.get("image") or image_query).strip()
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    if not top or not bottom:
        # Useful, context-specific backup captions if the model format is unusual.
        top = f"When {situation[:70].strip()}"
        bottom = random.choice([
            "And somehow I made it worse",
            "My last two brain cells resigned",
            "The consequences have entered the chat",
            "Character development was NOT in my budget",
            "I would like to unsubscribe from reality",
            "Even my backup plan needs a backup",
            "Somehow, this is still my fault"
        ])
        if not image_query:
            image_query = f"{situation} reaction photo"
    if not image_query:
        image_query = f"{situation} expression reaction photo"
    return top[:120], bottom[:120], image_query[:160]

def _safe_public_image_url(raw_url):
    """Reject non-HTTPS, credentialed, localhost and literal private-IP image URLs."""
    try:
        parsed = urlparse(str(raw_url or ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host
    except (TypeError, ValueError):
        return False

def _download_candidate(item):
    """Download one bounded image candidate; failures are intentionally non-fatal."""
    if not _safe_public_image_url(item.get("url", "")):
        return None
    try:
        with requests.get(item["url"], timeout=(2.5, 3.5), stream=True,
                          headers={"User-Agent": "Mozilla/5.0 MemeLab/1.0"}) as response:
            if response.status_code != 200:
                return None
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not content_type.startswith("image/"):
                return None
            length = response.headers.get("Content-Length")
            if length and int(length) > 5_000_000:
                return None
            chunks, total = [], 0
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 5_000_000:
                    return None
                chunks.append(chunk)
        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(io.BytesIO(b"".join(chunks))) as source:
            if source.width < 240 or source.height < 180 or source.width * source.height > 20_000_000:
                return None
            source.load()
            return source.convert("RGB")
    except Exception:
        return None

def find_image(situation, style, image_query=""):
    """Search several relevant photo queries and use the first valid real image."""
    def clean_query(value):
        value = re.sub(r"[^a-zA-Z0-9 ]+", " ", str(value or ""))
        return re.sub(r"\s+", " ", value).strip()[:100]

    situation_query = clean_query(situation)
    caption_query = clean_query(image_query)
    queries = []
    # Prefer the situation itself: AI-generated image descriptions can be vague or odd.
    for query in (
        f"{situation_query} reaction meme photo",
        f"{caption_query} reaction photo",
        f"{situation_query} funny relatable photo",
    ):
        query = clean_query(query)
        if query and query.lower() not in [q.lower() for q in queries]:
            queries.append(query)

    candidates = []
    seen = set()
    for query in queries:
        try:
            with DDGS() as ddgs:
                for item in ddgs.images(query, max_results=8):
                    url = item.get("image") or item.get("thumbnail")
                    if not _safe_public_image_url(url) or url in seen:
                        continue
                    seen.add(url)
                    title = str(item.get("title") or item.get("alt") or item.get("source") or "")
                    candidates.append({"url": url, "title": title})
            if len(candidates) >= 12:
                break
        except Exception:
            app.logger.info("Image search query failed; trying another relevant query")

    if candidates:
        keywords = set(re.findall(r"[a-z0-9]{3,}", f"{situation_query} {caption_query}".lower()))
        keywords -= {"the", "and", "for", "with", "when", "from", "this", "that", "photo", "image", "meme", "reaction", "funny", "person", "people", "someone"}
        random.shuffle(candidates)
        candidates.sort(key=lambda row: sum(word in row["title"].lower() for word in keywords), reverse=True)

        # Allow a little more time for real photo hosts; still bound concurrency and file size.
        pool = ThreadPoolExecutor(max_workers=5)
        futures = [pool.submit(_download_candidate, item) for item in candidates[:10]]
        try:
            for future in as_completed(futures, timeout=9):
                try:
                    result = future.result()
                    if result is not None:
                        for pending in futures:
                            if pending is not future:
                                pending.cancel()
                        pool.shutdown(wait=False, cancel_futures=True)
                        return result
                except Exception:
                    continue
        except TimeoutError:
            app.logger.info("Timed out while downloading image candidates")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    app.logger.error("No usable real photo found after all image searches")
    raise RuntimeError("REAL_PHOTO_NOT_FOUND")

def make_fallback(situation, style="Relatable"):
    """Create a clean, abstract fallback background; captions are drawn separately."""
    w, h = 1080, 1080
    palettes = [
        ((18, 13, 34), (255, 79, 189), (122, 92, 255)),
        ((10, 35, 39), (38, 220, 190), (255, 132, 74)),
        ((36, 17, 31), (255, 99, 71), (255, 197, 70)),
        ((20, 18, 48), (177, 105, 255), (70, 170, 255)),
        ((18, 30, 24), (165, 232, 94), (255, 112, 179)),
        ((35, 19, 45), (255, 91, 194), (255, 182, 72))
    ]
    bg, accent, accent2 = random.choice(palettes)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)

    # Soft geometric shapes provide visual texture without competing with captions.
    d.ellipse((690, -190, 1260, 380), fill=accent)
    d.ellipse((-230, 750, 370, 1350), fill=accent2)
    d.ellipse((760, 700, 1160, 1100), outline=accent2, width=12)
    d.arc((130, 240, 950, 1040), start=200, end=335, fill=accent, width=8)
    d.rounded_rectangle((85, 275, 995, 805), radius=60,
                        fill=(15, 12, 28), outline=(65, 52, 87), width=3)

    # Keep the central area intentionally quiet so the top and bottom captions
    # stay readable and the fallback never repeats the user's situation as text.
    center_font = get_font(180)
    mark = "✦"
    bbox = d.textbbox((0, 0), mark, font=center_font)
    d.text(((w - (bbox[2] - bbox[0])) // 2, 420), mark,
           font=center_font, fill=accent)
    small = get_font(25, False)
    label = "MEMELAB  /  " + str(style).upper()[:22]
    bbox = d.textbbox((0, 0), label, font=small)
    d.text(((w - (bbox[2] - bbox[0])) // 2, 750), label, font=small, fill=accent2)
    return im

def get_font(size, bold=True):
    candidates = [
        r"C:\Windows\Fonts\impact.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0,0), test, font=font, stroke_width=2)[2] <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)
    return lines or [text]

def render_meme(im, top, bottom, style):
    im = ImageOps.fit(im.convert("RGB"), (1080, 1080), method=Image.Resampling.LANCZOS)
    # Subtle dark overlay helps captions remain readable on busy images.
    overlay = Image.new("RGBA", im.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0,0,1080,245), fill=(0,0,0,55))
    od.rectangle((0,835,1080,1080), fill=(0,0,0,65))
    im = Image.alpha_composite(im.convert("RGBA"), overlay)
    d = ImageDraw.Draw(im)
    def caption(text, region_top, region_bottom):
        size = 76
        maxw = 990
        while size > 34:
            font = get_font(size)
            lines = wrap_text(d, text.upper(), font, maxw)
            line_h = size + 7
            if len(lines)*line_h <= region_bottom-region_top:
                break
            size -= 4
        line_h = size + 7
        y = region_top + (region_bottom-region_top-len(lines)*line_h)//2
        for line in lines:
            bbox = d.textbbox((0,0), line, font=font, stroke_width=4)
            x = (1080-(bbox[2]-bbox[0]))//2
            d.text((x,y), line, font=font, fill="white", stroke_width=5, stroke_fill="black")
            y += line_h
    caption(top, 20, 230)
    caption(bottom, 850, 1060)
    # Small, discreet maker tag.
    tagfont = get_font(19, False)
    d.rounded_rectangle((18, 1038, 170, 1070), radius=12, fill=(18,10,33,185))
    d.text((29,1044), "MEMELAB ✦", font=tagfont, fill=(255,117,209))
    return im.convert("RGB")

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemeLab — Cook Something</title>
<style>
:root{--bg:#090711;--panel:rgba(25,19,43,.78);--line:rgba(255,255,255,.10);--pink:#ff4fbd;--purple:#a78bfa;--text:#fbf7ff;--muted:#aaa3bd}
*{box-sizing:border-box}body{margin:0;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(ellipse at 12% 0%,#30134b 0,transparent 38%),radial-gradient(ellipse at 92% 16%,#3b123e 0,transparent 32%),var(--bg);min-height:100vh}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.13;background-image:radial-gradient(#fff 0.7px,transparent .7px);background-size:22px 22px;mask-image:linear-gradient(to bottom,#000,transparent 85%)}
.wrap{width:min(1120px,calc(100% - 32px));margin:auto;position:relative}.nav{display:flex;align-items:center;justify-content:space-between;padding:24px 0}.brand{display:flex;gap:11px;align-items:center;font-weight:900;letter-spacing:-.7px;font-size:22px}.logo{width:39px;height:39px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,var(--pink),#8b5cf6);box-shadow:0 0 30px #ff4fbd40;font-size:21px}.pill{border:1px solid var(--line);border-radius:99px;padding:8px 12px;color:#d5cce8;font-size:12px;background:#ffffff08}.hero{text-align:center;padding:42px 0 30px}.eyebrow{display:inline-flex;gap:8px;align-items:center;border:1px solid #ff4fbd55;background:#ff4fbd12;color:#ff9cdb;border-radius:99px;padding:8px 13px;font-size:12px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase}.spark{color:#ffd36d}.hero h1{font-size:clamp(43px,7vw,78px);line-height:.98;letter-spacing:-4px;margin:22px 0 17px;font-weight:950}.gradient{background:linear-gradient(95deg,#fff 10%,#ff8bd6 47%,#b9a0ff 85%);-webkit-background-clip:text;background-clip:text;color:transparent}.hero p{max-width:560px;margin:0 auto;color:var(--muted);font-size:16px;line-height:1.7}.layout{display:grid;grid-template-columns:.92fr 1.08fr;gap:20px;align-items:start;margin:24px 0 70px}.panel{border:1px solid var(--line);background:var(--panel);backdrop-filter:blur(18px);border-radius:25px;padding:24px;box-shadow:0 22px 80px #0003}.panelhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.panelhead h2{font-size:17px;margin:0;letter-spacing:-.3px}.step{font-size:11px;color:#b5a8d4;background:#ffffff0b;padding:7px 10px;border-radius:99px}.fieldlabel{font-size:12px;font-weight:800;color:#ddd5eb;display:block;margin:0 0 10px;letter-spacing:.35px}.textarea{width:100%;min-height:135px;resize:vertical;background:#0d0a17;border:1px solid #ffffff16;border-radius:16px;color:white;padding:16px;font:inherit;line-height:1.6;outline:none;transition:.2s}.textarea:focus{border-color:#ff65c2;box-shadow:0 0 0 4px #ff4fbd13}.hint{font-size:11px;color:#827995;margin-top:8px}.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 23px}.chip{border:1px solid #ffffff17;background:#ffffff06;color:#cfc6df;border-radius:99px;padding:9px 12px;font-size:12px;cursor:pointer;transition:.18s}.chip:hover{border-color:#ff8bd6;color:white;transform:translateY(-1px)}.chip.active{color:#fff;border-color:#ff63c4;background:linear-gradient(110deg,#ff4fbd2c,#9b75ff30);box-shadow:inset 0 0 0 1px #ff4fbd18}.btn{border:0;border-radius:15px;padding:15px 18px;font:inherit;font-size:14px;font-weight:900;cursor:pointer;transition:transform .18s,filter .18s;display:flex;align-items:center;justify-content:center;gap:10px}.btn:hover{transform:translateY(-2px);filter:brightness(1.08)}.btn:disabled{opacity:.55;cursor:wait;transform:none}.primary{width:100%;color:white;background:linear-gradient(100deg,#ff3eaf,#9b5cff);box-shadow:0 10px 30px #b42bba30}.tiny{font-size:11px;color:#817992;text-align:center;margin-top:13px}.preview{min-height:480px;display:flex;flex-direction:column}.previewbox{flex:1;min-height:390px;border:1px dashed #ffffff22;border-radius:19px;background:radial-gradient(ellipse at 50% 45%,#4b245d55,transparent 65%),#100c1b;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}.placeholder{text-align:center;padding:30px;color:#9a8eae}.placeholder .emoji{font-size:53px;filter:drop-shadow(0 0 20px #ff4fbd55)}.placeholder h3{font-size:17px;color:#e9e0f5;margin:17px 0 7px}.placeholder p{font-size:12px;line-height:1.6;max-width:230px;margin:auto}.memeimg{width:100%;height:100%;max-height:560px;object-fit:contain;display:block}.resultbar{display:flex;gap:10px;margin-top:14px}.resultbar .btn{flex:1}.secondary{color:#f8efff;border:1px solid #ffffff19;background:#ffffff09}.status{font-size:12px;color:#c4b7d7;margin-top:14px;min-height:18px}.status.error{color:#ff8da9}.loader{display:inline-block;width:15px;height:15px;border:2px solid #ffffff55;border-top-color:white;border-radius:50%;animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.footer{padding:0 0 28px;text-align:center;color:#6e667e;font-size:11px}.footer b{color:#a69bb7}.tagline{display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-top:25px;color:#9e94b1;font-size:11px}.tagline span{display:flex;gap:6px;align-items:center}.dot{color:#ff75c8}
@media(max-width:800px){.layout{grid-template-columns:1fr}.hero{padding-top:25px}.hero h1{letter-spacing:-2.4px}.preview{min-height:420px}.previewbox{min-height:320px}.nav{padding-top:16px}.panel{padding:19px}}
</style>
</head>
<body><div class="wrap">
<header class="nav"><div class="brand"><div class="logo">✳</div>meme<span class="gradient">lab</span></div><div class="pill">✦ YOUR HUMOUR, UPGRADED</div></header>
<section class="hero"><div class="eyebrow"><span class="spark">✦</span> THE INTERNET'S UNOFFICIAL THERAPY</div><h1>Your life is a joke.<br><span class="gradient">At least make it a good meme.</span></h1><p>Turn real-life chaos into simple, painfully relatable Gen Z memes. Easy to get. Hard not to send to the group chat.</p>
<div class="tagline"><span>✦ AI-powered punchlines</span><span><i class="dot">✦</i> Instant PNG</span><span>✦ Maximum group-chat energy</span></div></section>
<main class="layout">
<section class="panel"><div class="panelhead"><h2>Make it painfully funny</h2><span class="step">01 / CREATE</span></div>
<label class="fieldlabel" for="situation">WHAT HAPPENED? <span style="color:#ff80ce">*</span></label>
<textarea id="situation" class="textarea" maxlength="500" placeholder="e.g. me opening the syllabus one night before the exam..."></textarea><div class="hint">The more oddly specific, the better. Your lore is safe here.</div>
<div style="height:23px"></div><span class="fieldlabel">PICK YOUR INTERNET PERSONALITY</span>
<div class="chips" id="styles">
<button class="chip active" data-style="Relatable">🫠 Relatable</button><button class="chip" data-style="Savage">💅 Savage</button><button class="chip" data-style="Brainrot">🧠 Brainrot</button><button class="chip" data-style="Aura">🕶️ Aura</button><button class="chip" data-style="Classic">📼 Classic</button><button class="chip" data-style="Wholesome">🫶 Wholesome</button><button class="chip" data-style="Dramatic">🎬 Dramatic</button><button class="chip" data-style="Dark Humour">🖤 Dark humour</button><button class="chip" data-style="NPC Mode">🤖 NPC mode</button></div>
<button class="btn primary" id="create">✦ COOK MY MEME <span>↗</span></button><div class="tiny">Powered by AI. Judged by your group chat.</div>
</section>
<section class="panel preview"><div class="panelhead"><h2>Your masterpiece</h2><span class="step" id="badge">WAITING FOR THE COOK</span></div>
<div class="previewbox" id="preview"><div class="placeholder"><div class="emoji">🪄</div><h3>Your meme era starts here</h3><p>Drop a situation, choose your vibe, and let the algorithm cook.</p></div></div>
<div class="status" id="status" aria-live="polite"></div><div class="resultbar"><button class="btn secondary" id="remix" disabled>↻ Remix captions</button><button class="btn secondary" id="download" disabled>↓ Download PNG</button></div>
</section></main><footer class="footer">MADE FOR THE CHRONICALLY ONLINE <b>✦ MEMELAB</b> · Keep it funny, keep it kind.</footer></div>
<script>
let style="Relatable", lastSituation="", lastImage="";
const $=id=>document.getElementById(id);
document.querySelectorAll(".chip").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active"));b.classList.add("active");style=b.dataset.style;}));
async function createMeme(remix=false){
 const situation=$("situation").value.trim();
 if(!situation){$("status").textContent="Bestie, give me a situation to work with first 😭";$("status").className="status error";$("situation").focus();return;}
 lastSituation=situation; const btn=$("create"), remixBtn=$("remix");
 btn.disabled=true;remixBtn.disabled=true;$("download").disabled=true;
 $("badge").textContent=remix?"RE-COOKING":"COOKING...";
 $("preview").innerHTML='<div class="placeholder"><div class="loader" style="width:30px;height:30px;border-width:3px"></div><h3>Let them cook…</h3><p>AI is finding the punchline and the right reaction image. This can take a few seconds.</p></div>';
 $("status").className="status";$("status").textContent="Generating the punchline + hunting for the right vibe…";
 try{
  const res=await fetch("/api/create",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({situation,style,remix})});
  const contentType=res.headers.get("content-type")||"";
  let data;
  if(contentType.includes("application/json")){
   data=await res.json();
  }else{
   const body=(await res.text()).slice(0,240).replace(/<[^>]*>/g," ").replace(/\\s+/g," ").trim();
   if(res.status===503||res.status===502||res.status===500){
    throw new Error("MemeLab's server is having trouble right now. Please wait a moment and try again.");
   }
   throw new Error(body||"The server returned an unexpected response instead of JSON. Please try again.");
  }
  if(!res.ok)throw new Error(data.error||`Request failed (HTTP ${res.status}). Please try again.`);
  if(!data.image)throw new Error("The meme was created without an image. Please try Remix or generate again.");
  lastImage=data.image;
  $("preview").innerHTML=`<img class="memeimg" alt="Your generated meme" src="${data.image}?t=${Date.now()}">`;
  $("badge").textContent="IT'S GIVING ICONIC";$("status").textContent="Cooked. Send it to the group chat immediately. ✦";
  $("download").disabled=false;remixBtn.disabled=false;
 }catch(e){$("preview").innerHTML='<div class="placeholder"><div class="emoji">🫡</div><h3>The kitchen hit a snag</h3><p>Check the message below, then try again.</p></div>';$("badge").textContent="TRY AGAIN";$("status").className="status error";$("status").textContent=e.message;}
 finally{btn.disabled=false;remixBtn.disabled=false;}
}
$("create").addEventListener("click",()=>createMeme(false));
$("remix").addEventListener("click",()=>createMeme(true));
$("download").addEventListener("click",()=>{if(!lastImage)return;const a=document.createElement("a");a.href=lastImage;a.download="memelab-meme.png";document.body.appendChild(a);a.click();a.remove();});
$("situation").addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter")createMeme(false);});
</script></body></html>
"""

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.post("/api/create")
@limiter.limit("5 per minute; 30 per hour")
def create():
    if not request.is_json:
        return jsonify(error="Send the request as JSON."), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invalid request. Please send a situation and style."), 400
    raw_situation = payload.get("situation", "")
    if not isinstance(raw_situation, str):
        return jsonify(error="Situation must be text."), 400
    situation = re.sub(r"\s+", " ", raw_situation).strip()
    if len(situation) > 500:
        return jsonify(error="Keep your situation under 500 characters."), 413
    style = payload.get("style", "Relatable")
    if not isinstance(style, str):
        style = "Relatable"
    remix = payload.get("remix", False) is True
    if not situation:
        return jsonify(error="Enter a situation first."), 400
    if style not in STYLES:
        style = "Relatable"
    try:
        # A remix gets a fresh creative angle rather than reusing the same prompt.
        remix_angle = random.choice([
            "Use a fresh angle not used in a typical meme.",
            "Try an unexpected everyday twist.",
            "Make the joke more specific and surprising.",
            "Use a different punchline structure.",
            "Focus on an oddly relatable detail.",
        ]) if remix else None
        try:
            top, bottom, image_query = ask_groq(situation, style, variation=remix_angle)
        except Exception:
            # Keep meme creation usable if Groq is temporarily unavailable or not configured.
            app.logger.exception("AI captions unavailable; using local fallback captions")
            short_situation = situation[:65].strip().rstrip(" .,!?:;")
            top = f"Me: {short_situation}"[:120]
            bottom = random.choice([
                "My last two brain cells resigned",
                "The consequences have entered the chat",
                "Character development was NOT in my budget",
                "I would like to unsubscribe from reality",
                "Even my backup plan needs a backup",
                "Somehow, this is still my fault",
                "Task failed successfully"
            ])
            image_query = f"{situation} reaction photo"
        try:
            image = find_image(situation, style, image_query)
        except RuntimeError as image_error:
            if str(image_error) == "REAL_PHOTO_NOT_FOUND":
                return jsonify(error="I couldn’t find a usable real photo this time, so I didn’t create a fake placeholder. Please try again in a moment."), 503
            app.logger.exception("Image lookup failed")
            return jsonify(error="The real-photo search failed. Please try again in a moment."), 503
        except Exception:
            app.logger.exception("Image lookup failed")
            return jsonify(error="The real-photo search failed. Please try again in a moment."), 503
        rendered = render_meme(image, top, bottom, style)
        # Bound disk usage: remove files older than a day, then keep at most 149 old files.
        now = time.time()
        try:
            old_files = sorted(OUT.glob("*.png"), key=lambda path: path.stat().st_mtime)
            cutoff = now - 24 * 60 * 60
            for old_file in old_files:
                try:
                    if old_file.stat().st_mtime < cutoff:
                        old_file.unlink(missing_ok=True)
                except OSError:
                    continue
            remaining = sorted(OUT.glob("*.png"), key=lambda path: path.stat().st_mtime)
            for old_file in remaining[:max(0, len(remaining) - 149)]:
                try:
                    old_file.unlink(missing_ok=True)
                except OSError:
                    continue
        except OSError:
            app.logger.warning("Could not prune old generated images")
        name = f"{uuid.uuid4().hex}.png"
        rendered.save(OUT / name, format="PNG", optimize=True)
        return jsonify(top=top, bottom=bottom, image=f"/generated/{name}")
    except Exception:
        # Keep provider details, user prompts, and configuration out of public responses.
        app.logger.exception("Meme generation failed")
        return jsonify(error="Meme generation failed. Please try again shortly."), 502

@app.get("/generated/<path:filename>")
def generated(filename):
    return send_from_directory(OUT, filename)

if __name__ == "__main__":
    print("\nMemeLab is running at http://127.0.0.1:5000")
    print("Keep this PowerShell window open while using it. Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=5000, debug=False)

