# MemeLab ✳ — Gen Z Meme Studio

Turn oddly specific situations into shareable memes. MemeLab uses Groq AI to write punchy captions, searches for a reaction image, renders a square PNG, and lets you download it.

## Features

- AI-generated top/bottom captions based on your situation and chosen vibe
- Ten styles: Relatable, Savage, Brainrot, Aura, Classic, Wholesome, Dramatic, Dark Humour, Delulu, and NPC Mode
- One-click generation, caption remixing, and PNG download
- Responsive dark neon / glass UI
- API key read from an environment variable (never hardcode it in source)
- Fallback poster design if image search does not return a usable image

## Requirements

- Python 3.10+
- A Groq API key
- Internet access for the Groq API and image search

## Run on Windows PowerShell

```powershell
cd "C:\path\to\MemeLab_Competition_Ready"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:GROQ_API_KEY = Read-Host "Paste your Groq API key"
python app.py
```

Open http://127.0.0.1:5000. Keep the terminal open while the app is running. Stop it with Ctrl+C.

The key is only set for that PowerShell session. If you close the terminal, set it again next time. Do not paste your real key into `app.py`, `.env.example`, screenshots, or a public GitHub repository.

## Choose a different Groq model

The default model is `llama-3.3-70b-versatile`. If your Groq account does not have access to it or the provider changes model availability, set `GROQ_MODEL` to a model enabled in your Groq console before running the app:

```powershell
$env:GROQ_MODEL = "your-enabled-model-name"
```

## Publish to GitHub safely

1. Check that `.gitignore` is included.
2. Never commit `.env`, real API keys, or generated private files.
3. If a key was ever committed, revoke it and create a new one. Removing it in a later commit does not remove it from Git history.
4. Add screenshots after running the site locally.
5. This app is local-only by default; a public GitHub repository does not publish the running website. Deployment requires a hosting provider and secure server-side secret configuration.

## Notes

Image search is best-effort and results can vary. Check image licensing and platform terms before publishing generated memes publicly. If the API or image search is rate-limited, wait and try again. This is a starter project; before public deployment, add rate limiting, request validation, and production hosting configuration.
