# Deploy to Railway

Your app is ready to deploy! Here's what I've set up:

✅ Git repository initialized
✅ Deployment files created (Procfile, railway.json, .gitignore)
✅ App configured for production (uses PORT environment variable)

## Quick Deploy Steps

### 1. Push to GitHub (2 minutes)

```bash
# Create a new repo at https://github.com/new
# Name it: thumbnail-generator-v2
# Then run:

git remote add origin https://github.com/YOUR-USERNAME/thumbnail-generator-v2.git
git branch -M main
git push -u origin main
```

### 2. Deploy on Railway (3 minutes)

Railway new project page is opening in your browser...

1. Click "Deploy from GitHub repo"
2. Select your `thumbnail-generator-v2` repo
3. Railway will auto-detect it's a Python app and deploy

### 3. Add Environment Variables

In Railway project settings → Variables, add these from your `.env` file:

```
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here
REPLICATE_API_TOKEN=your_key_here
IDEOGRAM_API_KEY=your_key_here
FAL_KEY=your_key_here
TOGETHER_API_KEY=your_key_here
```

### 4. Done!

Railway will give you a URL like `https://thumbnail-generator-v2.railway.app`

## Alternative: Quick Test with ngrok (30 seconds)

For immediate testing without deployment:

```bash
# Install ngrok
brew install ngrok

# Start your local server (if not running)
venv/bin/python app.py &

# Tunnel it
ngrok http 5050
```

This gives you a public URL instantly, but requires keeping your computer running.

## Cost

Railway free tier: $5 credit/month (should be plenty for testing)
Railway Pro: $5/month base + usage (recommended for production)
