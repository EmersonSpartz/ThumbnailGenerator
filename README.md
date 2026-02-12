# Thumbnail Generator v2

An AI-powered YouTube thumbnail generator that learns from your successes.

## Features

### 1. **Favorites System** ⭐
Mark thumbnails that work well. The system learns from your favorites and uses them to guide future generation.

### 2. **Variation Generation** 🔄
Click on any favorite thumbnail to generate more like it. Choose from three styles:
- **Similar** - Close variations of the original
- **Explore** - More creative interpretations
- **Remix** - Combines successful elements with new ideas

### 3. **Multiple Image Models** 🎨
- **Gemini NanoBanana** - Google's image model, good all-around
- **Flux Schnell** - Fast, high-quality with great composition
- **SDXL Lightning** - Very fast stylized images
- **Ideogram** - Best for thumbnails with text

### 4. **Smart Learning**
- Tracks which categories perform well
- Avoids generating duplicate concepts
- Balances variety across categories
- Uses your favorites to improve prompts

## Quick Start

### 1. Install Dependencies
```bash
cd thumbnail_generator_v2
pip install -r requirements.txt
```

### 2. Set Up API Keys
```bash
cp .env.example .env
# Edit .env and add your API keys
```

**Required:**
- `ANTHROPIC_API_KEY` - Get from [Anthropic Console](https://console.anthropic.com/)
- `GOOGLE_API_KEYS` - Get from [Google AI Studio](https://makersuite.google.com/app/apikey)

**Optional (for more models):**
- `REPLICATE_API_TOKEN` - Get from [Replicate](https://replicate.com/account/api-tokens)
- `IDEOGRAM_API_KEY` - Get from [Ideogram](https://ideogram.ai/api)

### 3. Run the App
```bash
python app.py
```

### 4. Open in Browser
Go to: http://localhost:5000

## How to Use

### Generating Thumbnails
1. Enter your video title(s) - one per line
2. Optionally paste your script for better context
3. Choose how many thumbnails to generate
4. Pick an image model
5. Click "Generate Thumbnails"

### Building Your Favorites
1. When you see a thumbnail you like, click "⭐ Favorite"
2. Add notes about why it works (optional but helpful)
3. The system will learn from your preferences

### Generating Variations
1. First, add a thumbnail to favorites
2. Click "🔄 Variations" on any favorited thumbnail
3. Choose a variation style
4. Generate more thumbnails in that direction

### Comparing Models
1. Go to the "Compare Models" tab
2. Paste an image generation prompt
3. Click "Compare All Models"
4. See how each model interprets the same prompt

## Tips for Best Results

### Video Titles
- Enter 2-3 title options for more variety
- More specific titles = more targeted thumbnails

### Using the Script
- Paste your full script for best results
- Claude will identify key moments and visuals

### Favorites Strategy
- Be selective - only favorite thumbnails you'd actually use
- Add notes about what works ("great contrast", "eye-catching", etc.)
- The more favorites you add, the better future results

### Model Selection
- **Gemini** - Good default choice
- **Flux** - Best for photorealistic images
- **Ideogram** - Use when you need text on the thumbnail
- **SDXL** - Good for artistic/stylized thumbnails

## File Structure

```
thumbnail_generator_v2/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── README.md             # This file
├── lib/
│   ├── config.py         # Settings and configuration
│   ├── claude_client.py  # Claude AI integration
│   ├── image_generator.py # Multi-model image generation
│   ├── favorites.py      # Favorites/learning system
│   └── freshness.py      # Duplicate avoidance
├── data/
│   ├── prompting_guide.md # Image prompt templates
│   ├── favorites.json    # Your saved favorites
│   └── freshness_tracker.json
├── templates/
│   └── index.html        # Web interface
└── output/               # Generated thumbnails
```

## Troubleshooting

### "No API keys configured"
Make sure your `.env` file exists and has valid keys.

### "Quota exhausted"
You've hit rate limits. Options:
- Wait a few minutes
- Add more API keys (comma-separated in GOOGLE_API_KEYS)
- Use a different model

### Thumbnails look wrong
- Try a different model
- Check the prompting guide in `data/prompting_guide.md`
- Add more context via the script field

### Generation is slow
- Claude's extended thinking takes time for better results
- Reduce `THINKING_BUDGET_TOKENS` in .env for faster (but potentially lower quality) results
- Use Flux Schnell or SDXL Lightning for faster image generation
