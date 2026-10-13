import os, io, json, random, re, time, uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from PIL import Image, ImageDraw, ImageFont, ImageOps
from ddgs import DDGS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "static" / "generated"
OUT.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

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
    "Delulu": "delusional confidence, main-character energy, unserious optimism",
    "NPC Mode": "deadpan repetitive internet humour and oddly specific reactions"
}

def ask_groq(situation, style):
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing Groq API key. Restart using the PowerShell launcher and enter your key.")
    system = """You are the funniest, most online meme writer in a Gen Z group chat. Create highly shareable meme captions.
Return ONLY valid JSON with keys top and bottom. Each value must be a short caption, ideally 2-9 words.
Be specific to the user's situation, punchy, fresh, natural, and readable on an image. Avoid generic jokes, hashtags, explaining the joke, and forced slang. Do not use slurs or target protected groups. Don't put quote marks around captions."""
    user = f"""Situation: {situation}
Vibe: {style} — {STYLES.get(style, STYLES['Relatable'])}
Write a top line that sets up the situation and a bottom line that lands the punchline. They should work together."""
    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.95, "max_tokens": 180,
              "messages": [{"role":"system","content":system},{"role":"user","content":user}],
              "response_format": {"type": "json_object"}},
        timeout=30
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"Groq API error ({response.status_code}): {str(detail)[:260]}")
    content = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
    except Exception:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise RuntimeError("AI returned an unexpected format. Try again.")
        data = json.loads(match.group(0))
    top = str(data.get("top", "")).strip().strip('"')
    bottom = str(data.get("bottom", "")).strip().strip('"')
    if not top or not bottom:
        raise RuntimeError("AI returned an empty caption. Try again.")
    return top[:120], bottom[:120]

def find_image(situation, style):
    queries = [
        f"{situation} funny reaction image",
        f"funny reaction meme {situation}",
        "funny cat reaction meme"
    ]
    candidates = []
    try:
        with DDGS() as ddgs:
            for query in queries:
                try:
                    results = ddgs.images(query, max_results=7)
                    for item in results:
                        url = item.get("image") or item.get("thumbnail")
                        if url and url.startswith("https://"):
                            candidates.append(url)
                except Exception:
                    continue
    except Exception:
        pass
    random.shuffle(candidates)
    for url in candidates[:16]:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 MemeLab/1.0"})
            if r.status_code != 200 or len(r.content) > 7_000_000:
                continue
            im = Image.open(io.BytesIO(r.content))
            im.load()
            if im.width < 240 or im.height < 180:
                continue
            return im.convert("RGB")
        except Exception:
            continue
    # Reliable visual fallback so the app can still make a meme if image search is unavailable.
    return make_fallback(situation)

def make_fallback(situation):
    w, h = 1000, 700
    im = Image.new("RGB", (w, h), (27, 17, 52))
    d = ImageDraw.Draw(im)
    d.ellipse((620, -130, 1120, 370), fill=(255, 46, 166))
    d.ellipse((-140, 410, 430, 980), fill=(111, 61, 255))
    d.rounded_rectangle((95, 110, 905, 590), radius=45, fill=(36, 26, 68), outline=(255, 82, 186), width=5)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 38)
    except Exception:
        font = ImageFont.load_default()
    label = "THE VIBE IS:"
    d.text((145, 190), label, font=font, fill=(255, 104, 204))
    words = situation.split()
    lines, line = [], ""
    for word in words:
        if len(line + " " + word) > 27:
            lines.append(line); line = word
        else:
            line = (line + " " + word).strip()
    if line: lines.append(line)
    for i, ln in enumerate(lines[:5]):
        d.text((145, 260+i*52), ln, font=font, fill=(255,255,255))
    d.text((145, 510), "MEMELAB • MAIN CHARACTER MOMENT", font=ImageFont.load_default(), fill=(188,170,255))
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
<section class="hero"><div class="eyebrow"><span class="spark">✦</span> THE INTERNET'S UNOFFICIAL THERAPY</div><h1>Don't explain it.<br><span class="gradient">Meme it.</span></h1><p>Turn your oddly specific life situations into dangerously shareable memes. One prompt. One vibe. Zero effort.</p>
<div class="tagline"><span>✦ AI-powered punchlines</span><span><i class="dot">✦</i> Instant PNG</span><span>✦ Maximum group-chat energy</span></div></section>
<main class="layout">
<section class="panel"><div class="panelhead"><h2>Make it painfully funny</h2><span class="step">01 / CREATE</span></div>
<label class="fieldlabel" for="situation">WHAT HAPPENED? <span style="color:#ff80ce">*</span></label>
<textarea id="situation" class="textarea" maxlength="500" placeholder="e.g. me opening the syllabus one night before the exam..."></textarea><div class="hint">The more oddly specific, the better. Your lore is safe here.</div>
<div style="height:23px"></div><span class="fieldlabel">PICK YOUR INTERNET PERSONALITY</span>
<div class="chips" id="styles">
<button class="chip active" data-style="Relatable">🫠 Relatable</button><button class="chip" data-style="Savage">💅 Savage</button><button class="chip" data-style="Brainrot">🧠 Brainrot</button><button class="chip" data-style="Aura">🕶️ Aura</button><button class="chip" data-style="Classic">📼 Classic</button><button class="chip" data-style="Wholesome">🫶 Wholesome</button><button class="chip" data-style="Dramatic">🎬 Dramatic</button><button class="chip" data-style="Dark Humour">🖤 Dark humour</button><button class="chip" data-style="Delulu">💋 Delulu</button><button class="chip" data-style="NPC Mode">🤖 NPC mode</button></div>
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
  const data=await res.json();if(!res.ok)throw new Error(data.error||"Something went wrong.");
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
def create():
    payload = request.get_json(silent=True) or {}
    situation = re.sub(r"\s+", " ", str(payload.get("situation", ""))).strip()[:500]
    style = str(payload.get("style", "Relatable"))
    if not situation:
        return jsonify(error="Enter a situation first."), 400
    if style not in STYLES:
        style = "Relatable"
    try:
        top, bottom = ask_groq(situation, style)
        image = find_image(situation, style)
        rendered = render_meme(image, top, bottom, style)
        name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        rendered.save(OUT / name, format="PNG", optimize=True)
        return jsonify(top=top, bottom=bottom, image=f"/generated/{name}")
    except Exception as e:
        return jsonify(error=str(e)[:400]), 502

@app.get("/generated/<path:filename>")
def generated(filename):
    return send_from_directory(OUT, filename)

if __name__ == "__main__":
    print("\nMemeLab is running at http://127.0.0.1:5000")
    print("Keep this PowerShell window open while using it. Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=5000, debug=False)

