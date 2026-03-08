# Drew's Setup Guide

## What This Gets You
When the thumbnail generator (or any app) breaks, you can open Claude Code and say:
"the thumbnail generator is down, fix it and deploy"
...and Claude will check the logs, find the problem, fix it, and redeploy. No coding needed.

## One-Time Setup (15 min)

### 1. Emerson adds you to the GitHub repo
Emerson needs to run this (or do it on github.com):
```
gh api repos/EmersonSpartz/ThumbnailGenerator/collaborators/DREWS_GITHUB_USERNAME -X PUT -f permission=push
```
You'll get an email invite — accept it.

### 2. Clone the project
Open Terminal and paste:
```
cd ~/Downloads && git clone https://github.com/EmersonSpartz/ThumbnailGenerator.git
cd ThumbnailGenerator
```

### 3. Get the .env file from Emerson
Ask Emerson to send you the `.env` file. Put it in the ThumbnailGenerator folder.
This has all the API keys (Google, Anthropic, OpenAI, etc.)

### 4. Link to Railway
```
npm install -g @railway/cli
railway login
railway link
```
Select: ThumbnailGenerator > production > web

### 5. You're done!
Open Claude Code in the ThumbnailGenerator folder and talk to it like normal.

## Common Things to Say to Claude

- "the thumbnail generator is down, check the logs and fix it"
- "check if the Railway deploy is healthy"
- "the disk is probably full again, clean it up"
- "redeploy the app"
- "check the Railway logs for errors"

## Quick Reference

- **App URL**: https://web-production-d277.up.railway.app
- **Health check**: https://web-production-d277.up.railway.app/health
- **Clean disk**: `curl -X POST "https://web-production-d277.up.railway.app/api/cleanup-output?keep=10"`
- **Check logs**: `railway logs -n 50` (in the project folder)
