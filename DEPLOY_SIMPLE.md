# Deploy in 5 Minutes

Everything is ready. Just need to copy your API keys and click a few buttons.

## Option 1: Railway (Recommended - Persistent, Always On)

### Step 1: Push to GitHub (2 min)
```bash
# I opened https://github.com/new in your browser
# Name it: thumbnail-generator-v2
# Make it Private
# Click "Create repository"

# Then run these commands:
git remote add origin https://github.com/YOUR-USERNAME/thumbnail-generator-v2.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy on Railway (2 min)
```bash
# I opened https://railway.app/new in your browser
# Click "Deploy from GitHub repo"
# Authorize Railway to access GitHub
# Select "thumbnail-generator-v2"
# Railway auto-detects Python and deploys
```

### Step 3: Add API Keys (1 min)
In Railway project → Variables tab, paste these:

```
ANTHROPIC_API_KEY=<copy from .env>
OPENAI_API_KEY=<copy from .env>
GOOGLE_API_KEY=<copy from .env>
REPLICATE_API_TOKEN=<copy from .env>
IDEOGRAM_API_KEY=<copy from .env>
FAL_KEY=<copy from .env>
TOGETHER_API_KEY=<copy from .env>
```

Railway gives you a URL like: `https://thumbnail-generator-v2-production.up.railway.app`

Send that to Drew!

---

## Option 2: ngrok (Instant - But Requires Your Computer Running)

If you need it RIGHT NOW while Railway deploys:

```bash
# 1. Get ngrok auth token (I opened the page for you)
# Copy your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken

# 2. Configure ngrok
ngrok config add-authtoken YOUR_TOKEN_HERE

# 3. Start server
venv/bin/python app.py &

# 4. Tunnel it
ngrok http 5050
```

You'll get a URL like `https://abc123.ngrok-free.app` - send that to Drew!

Note: This URL only works while your computer is on and running.

---

## Comparison

| Method | Setup Time | Persistence | Cost |
|--------|-----------|-------------|------|
| Railway | 5 min | Always on | $5/mo |
| ngrok | 30 sec | While computer on | Free |

**Recommendation**: Do ngrok now for immediate testing, Railway for production use.
