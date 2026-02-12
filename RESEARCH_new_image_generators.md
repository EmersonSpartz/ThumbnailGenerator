# New Image Generators Research

## Quick Summary

Your app currently uses: **Gemini, Flux (Replicate), SDXL (Replicate), Midjourney (LegNext)**

Here's everything worth adding, ranked by value.

---

## TOP PICKS — Add These First

### 1. Pikzels — Purpose-Built YouTube Thumbnail API
- **URL:** https://pikzels.com
- **What:** The only product with AI models trained *exclusively* on high-performing YouTube thumbnails. Three proprietary models (pkz-1, pkz-2, pkz-3). Used by 570K+ creators including Mark Rober and Veritasium.
- **HAS AN API:** Yes! Full REST API at `https://api.pikzels.com` — documented at docs.pikzels.com
- **Pricing:** ~$0.10-0.27/thumbnail depending on plan (Essential $20/mo for 200 credits, Premium $40/mo for 1000, Ultimate $80/mo for 3000)
- **Why it's #1:** This is literally what you asked for — a model fine-tuned on YouTube thumbnails with a real API. 1,548 Trustpilot reviews, overwhelmingly 5-star. Claims 30-second generation.
- **Integration:** REST API with `X-Api-Key` header. Endpoints for `/v1/thumbnail`, face swap, recreate, etc.

### 2. fal.ai — One API, Every Top Model
- **URL:** https://fal.ai
- **What:** API aggregator with 600+ models. One integration gives you Flux 2, Recraft V3, Ideogram V3, Seedream 4.5, and more. 4-10x faster inference than Replicate.
- **Python SDK:** `pip install fal`
- **Pricing:** Pay-per-output. ~$0.01-0.05/image for most models.
- **Bonus:** They have a **YouTube Thumbnails LoRA** endpoint specifically: `fal-ai/image-editing/youtube-thumbnails` built on Flux Kontext
- **Why add it:** Replaces/supplements Replicate with faster speeds, more models, and often cheaper pricing. The thumbnail-specific endpoint is icing on the cake.

### 3. OpenAI GPT Image 1.5
- **URL:** https://platform.openai.com
- **What:** Currently the #1 rated image generation model overall. Exceptional text rendering, complex compositions, marketing-style images.
- **Python SDK:** `pip install openai` (you already have this key)
- **Pricing:** $0.01 (low), $0.04 (medium), $0.17 (high quality)
- **Why add it:** You already have an OpenAI key. Best-in-class for complex scenes. The "low" quality tier at $0.01 is great for drafts.

### 4. Flux Thumbnails LoRA (Replicate)
- **URL:** https://replicate.com/justmalhar/flux-thumbnails-v2
- **What:** Open-source Flux LoRA fine-tuned specifically on YouTube thumbnails. Trigger word: `YTTHUMBNAIL`. 15,600+ runs.
- **Pricing:** ~$0.017/image on Replicate
- **Why add it:** You already use Replicate — this is literally a 5-line code change. A thumbnail-specific model in your existing pipeline.

### 5. Ideogram 3.0 — Best Text-in-Image
- **URL:** https://ideogram.ai
- **What:** ~90% text rendering accuracy vs ~30% for most models. Best for thumbnails that need bold titles rendered in the image itself.
- **Pricing:** ~$0.04/image
- **Why add it:** If you ever want text baked into the image (not overlaid later), nothing else comes close. Also available through fal.ai and Together.ai.

---

## STRONG ADDITIONS — Worth Adding

### 6. Recraft V3 — Best for Design/Typography
- **URL:** https://www.recraft.ai
- **Python SDK:** Available
- **Pricing:** $0.04/raster, $0.08/vector
- **Why:** Purpose-built for graphic design. Has a dedicated YouTube thumbnails feature. Best vector art + typography of any model. Also on fal.ai.

### 7. Together.ai — Free Flux for Drafts
- **URL:** https://www.together.ai
- **Python SDK:** `pip install together`
- **Pricing:** Flux Schnell is **FREE** (unlimited, 3-month promo). Paid models competitive with Replicate.
- **Why:** Free draft generation. Zero cost for preview/iteration thumbnails.

### 8. Runware — Cheapest Bulk Generation
- **URL:** https://runware.ai
- **Python SDK:** `pip install runware`
- **Pricing:** Flux Schnell at **$0.0006/image** (~1,666 images per $1). $10 free credit.
- **Why:** When you want to generate tons of variations cheaply. 10-50x cheaper than Replicate for the same models.

### 9. Seedream 4.5 (ByteDance)
- **Available via:** fal.ai, Replicate, BytePlus API
- **Pricing:** $0.04/image, up to 4K resolution
- **Why:** Strong photorealism + text rendering. 200 free trial images via BytePlus.

---

## THUMBNAIL-SPECIFIC PRODUCTS (No API / Limited Use)

| Product | URL | Has API? | Notes |
|---------|-----|----------|-------|
| **1of10** | 1of10.com | No | YouTube research platform with thumbnail gen. $69/mo Pro tier. No API. |
| **ThumbnailVault** | thumbnailvault.com | No | NOT a generator. Free inspiration library of top-performing thumbnails. |
| **Thumbly AI** | thumbly.ai | No | **SHUT DOWN.** Appears defunct. |
| **vidIQ** | vidiq.com | No | Has thumbnail builder but no API for it. |
| **TubeBuddy** | tubebuddy.com | No | Template editor, not AI generation. Has a CTR analyzer though. |
| **MangooFX** | mangoofx.com | No | "DigitalMe" face training. Proprietary models MGX-1/2/3. No API. |
| **Thumbnail.ai** | thumbnail.ai | No | Basic AI generator. Limited info. |
| **Thumber.app** | thumber.app | **Yes!** | REST API + SDKs. 12K+ creators. Worth investigating further. |
| **Artificial Studio** | artificialstudio.ai | **Yes!** | API available. $0.04/thumbnail. Cheap dark horse option. |
| **OpusClip** | opus.pro | Partial | Uses GPT-4o. Free tier. Broader video tool. |
| **ThumbnailCreator** | thumbnailcreator.com | No | Face training, person swap. $29/mo for 500 thumbs. |
| **Thumbmagic** | thumbmagic.co | No | Trained on 2.3M thumbnails. Updates models every 48 hours. |

---

## OPEN-SOURCE THUMBNAIL LORAS (For Self-Hosting or Replicate)

| Model | Platform | Base | Training Data | Trigger Word |
|-------|----------|------|---------------|-------------|
| **justmalhar/flux-thumbnails-v2** | Replicate + HuggingFace | Flux Dev | YouTube thumbnails | `YTTHUMBNAIL` |
| **fal/Youtube-Thumbnails-Kontext-Dev-LoRA** | fal.ai + HuggingFace | Flux Kontext | YouTube thumbnails | `Generate youtube thumbnails using text "YOUR TEXT"` |
| **Youtube Thumbnails Flux** | CivitAI #739869 | Flux Dev | 1,000 YT thumbnails | `thumbnaillora` |
| **Youtube Thumbnail Generator** | CivitAI #1171090 | Flux Dev | 100 thumbnails | — |
| **itzzdeep/youtube-thumbnails-sdxl-lora-v3** | HuggingFace | SDXL | YouTube thumbnails | `<s0><s1>` |
| **[FLUX] Thumbnail Design** | CivitAI #880467 | Flux | Design-focused | — |

---

## BUDGET / VOLUME API PROVIDERS

For when you want the same models but cheaper:

| Provider | Flux Schnell Price | Flux Dev/Pro Price | Python SDK | Notes |
|----------|-------------------|-------------------|------------|-------|
| **Runware** | $0.0006/img | $0.0038/img | `pip install runware` | Cheapest. 400K+ models. $10 free. |
| **Fireworks** | $0.0014/img | $0.014/img | REST API | Fast. Good Kontext support. |
| **SiliconFlow** | — | $0.015/img (Kontext Dev) | OpenAI-compatible API | Uses `openai` package. |
| **Together** | **FREE** | $0.04/MP | `pip install together` | Free Schnell for 3 months. |
| **Novita** | — | $0.0015/img (SD) | REST API | 10K+ models. Rock bottom prices. |
| **GetImg** | $0.0006/1M pixelsteps | $0.03/img | REST API | Clean API, good docs. |
| **WaveSpeedAI** | $0.002/img | $0.035/img | REST API | 600+ models. |
| **Replicate** (current) | $0.003/img | $0.03-0.055/img | `pip install replicate` | What you already use. |

---

## NOT WORTH ADDING

| Service | Why Skip |
|---------|----------|
| NightCafe | No API. Web only. |
| Canva API | AI gen locked to their platform. |
| Adobe Firefly | Enterprise pricing ($5K+/year). |
| Shutterstock AI | Subscription-locked. |
| Midjourney (official) | Still no official API in 2026. |

---

## MY RECOMMENDED INTEGRATION ORDER

1. **Pikzels** — The only API with models trained on YouTube thumbnails. This is exactly what you asked for.
2. **Flux Thumbnails LoRA** — Trivial to add (you already use Replicate). Thumbnail-specific.
3. **fal.ai** — One API key → access to Flux 2, Recraft V3, Ideogram 3.0, Seedream 4.5, AND their YouTube Thumbnails endpoint.
4. **GPT Image 1.5** — You have the OpenAI key. Top-rated model. Easy win.
5. **Together.ai** — Free Flux Schnell for unlimited draft generation.
6. **Recraft V3** — If you want design-quality thumbnails with good typography.
