#!/usr/bin/env python3
"""
Fine-tune a Flux model on AI Species thumbnails.
"""
import os
import replicate
from pathlib import Path
from dotenv import load_dotenv

# Load API token from .env file - never commit your actual token!
load_dotenv()
# Token will be loaded from REPLICATE_API_TOKEN in .env

def upload_training_data():
    """Upload the zip file to Replicate."""
    zip_path = Path(__file__).parent / "aispecies_thumbnails.zip"

    if not zip_path.exists():
        print(f"Error: {zip_path} not found")
        return None

    print(f"Uploading {zip_path.name} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)...")

    # Upload the file
    with open(zip_path, "rb") as f:
        file_url = replicate.files.create(f)

    print(f"Uploaded: {file_url}")
    return file_url

def start_training(input_images_url):
    """Start the fine-tuning process."""
    print("\nStarting fine-tune training...")
    print("This will take about 2 minutes and cost ~$1.50")

    # Create a model to store the fine-tune
    # First check if it already exists
    model_name = "aispecies-thumbnails"
    owner = "emersonspartz"  # Your Replicate username

    training = replicate.trainings.create(
        # Use the fast Flux trainer
        version="ostris/flux-dev-lora-trainer:d995297071a44dcb72244e6c19462111649ec86a9ff7e6b8a60e06e64c5c7bbc",
        input={
            "input_images": input_images_url,
            "trigger_word": "AISPECIES",  # Unique trigger word for your style
            "steps": 1000,  # Recommended
            "learning_rate": 0.0004,  # Default
            "batch_size": 1,
            "resolution": "1024",
            "autocaption": True,  # Let the trainer auto-caption
            "autocaption_prefix": "a youtube thumbnail in the style of AISPECIES, ",
        },
        # Where to save the trained model
        destination=f"{owner}/{model_name}"
    )

    return training

def main():
    print("=" * 50)
    print("AI Species Thumbnail Fine-Tuner")
    print("=" * 50)

    # Step 1: Upload training data
    file_url = upload_training_data()
    if not file_url:
        return

    # Step 2: Start training
    print("\n" + "=" * 50)
    print("IMPORTANT: Before running training, you need to:")
    print("1. Go to https://replicate.com/account")
    print("2. Create a model called 'aispecies-thumbnails'")
    print("3. Set it to 'private' if you want")
    print("=" * 50)
    print(f"\nTraining data URL: {file_url}")
    print("\nTo start training, run this command:")
    print(f"""
curl -s -X POST https://api.replicate.com/v1/models/ostris/flux-dev-lora-trainer/versions/d995297071a44dcb72244e6c19462111649ec86a9ff7e6b8a60e06e64c5c7bbc/trainings \\
  -H "Authorization: Bearer $REPLICATE_API_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "destination": "YOUR_USERNAME/aispecies-thumbnails",
    "input": {{
      "input_images": "{file_url}",
      "trigger_word": "AISPECIES",
      "steps": 1000,
      "autocaption": true,
      "autocaption_prefix": "a youtube thumbnail in the style of AISPECIES, "
    }}
  }}'
""")

if __name__ == "__main__":
    main()
