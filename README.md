# MemeLab ✳ — Gen Z Meme Studio

**Turn real-life chaos into simple, context-aware, shareable memes.**

🌐 **Live website:** https://memelab-7d92.onrender.com  
💻 **GitHub repository:** https://github.com/abhinavprasadsingh/MemeLab  
🚀 **Render deployments:** https://dashboard.render.com/web/srv-db73jgrncjis73fdg3og/deploys

MemeLab uses Groq AI to create short, readable meme captions, searches for a context-relevant reaction image, renders a square PNG, and lets you download it. Each generation gets a fresh creative angle, though AI results and image-search matches can still vary.

## Features

- Context-aware top and bottom captions designed to be easy to understand
- Fresh creative angles for each generation and caption remix
- Nine humour styles: Relatable, Savage, Brainrot, Aura, Classic, Wholesome, Dramatic, Dark Humour, and NPC Mode
- Context-focused image search with a designed fallback when a usable image cannot be found
- One-click generation, caption remixing, and PNG download
- Responsive dark neon interface
- API keys read from environment variables; no secret should be hardcoded in source

## Live deployment

Open the site: **https://memelab-7d92.onrender.com**

The project is configured for Render using the included `render.yaml` and `Procfile`. The current Render service is named `MemeLab`. On the Free plan, the service may take a little time to wake up after inactivity.

### Required Render environment variable

Set this in the Render service's **Environment** settings:

- `GROQ_API_KEY`: your private Groq API key

Optional:

- `GROQ_MODEL`: a model name enabled for your Groq account. If omitted, the app uses `llama-3.3-70b-versatile` as its code default.

Never put the real key in GitHub, README files, screenshots, or chat messages. If a key was exposed, revoke it and create a replacement in the Groq console.

## Run locally (Windows PowerShell)

1. Install Python 3.10 or newer.
2. Clone the repository and enter its folder:

```powershell
git clone https://github.com/abhinavprasadsingh/MemeLab.git
cd MemeLab
```

3. Create and activate a virtual environment, then install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Set your API key in the current PowerShell session and start the app:

```powershell
$env:GROQ_API_KEY = Read-Host "Paste your Groq API key"
# Optional: set a model available to your Groq account
# $env:GROQ_MODEL = "your-enabled-model-name"
python app.py
```

5. Open http://127.0.0.1:5000 in your browser. Keep the terminal open while using the app. Press Ctrl+C to stop it.

The environment variable only lasts for that PowerShell session. Set it again when opening a new terminal.

## Configuration

A safe placeholder example is included in `.env.example`. The app reads `GROQ_API_KEY` and optional `GROQ_MODEL` from environment variables. The app does not automatically load a `.env` file, so setting environment variables in PowerShell or your hosting provider is required unless you add a dotenv loader.

## Deployment files

- `render.yaml` — Render service configuration
- `Procfile` — production start command (`gunicorn app:app`)
- `requirements.txt` — Python dependencies
- `.env.example` — safe environment-variable template
- `.gitignore` — ignores local secrets, virtual environments, and generated memes

## Troubleshooting

- **“Missing Groq API key”**: add `GROQ_API_KEY` to Render Environment settings, save, and redeploy/restart the service.
- **Groq API/model errors**: confirm the key is active and `GROQ_MODEL` names a model available to your account.
- **Image does not exactly match the prompt**: image search is best-effort; it cannot guarantee the exact image someone imagines. Try a more specific situation.
- **Site is slow to open**: a free hosted service may need to wake up after inactivity.

## Security and image use

- Never commit `.env`, API keys, or other credentials.
- If a key was ever exposed, revoke it and create a new one. Deleting it in a later commit does not remove it from Git history.
- Image search results may have usage restrictions. Check licensing and platform terms before reposting images publicly.
- Before a larger public launch, consider rate limiting and monitoring API usage.

---

Made for the chronically online ✦ Keep it funny, keep it kind.
