"""Configuration and settings for the thumbnail generator."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # API Keys
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY', '')
        self.google_api_keys = self._parse_google_keys()

        # Model settings
        self.claude_model = os.getenv('CLAUDE_MODEL', 'claude-opus-4-5-20251101')
        self.thinking_budget_tokens = int(os.getenv('THINKING_BUDGET_TOKENS', '10000'))

        # Directories - use persistent volume on Railway, local dirs otherwise
        self.base_dir = Path(__file__).parent.parent
        persistent_dir = Path('/app/persistent')
        if persistent_dir.exists():
            # Railway deployment - use persistent volume
            self.data_dir = persistent_dir / 'data'
            self.output_dir = persistent_dir / 'output'
        else:
            # Local development
            self.data_dir = self.base_dir / 'data'
            self.output_dir = self.base_dir / 'output'
        self.templates_dir = self.base_dir / 'templates'

        # Favorites database
        self.favorites_db_path = self.data_dir / 'favorites.json'

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _parse_google_keys(self) -> list:
        """Parse Google API keys from environment (comma-separated)."""
        keys_str = os.getenv('GOOGLE_API_KEYS', '')
        if not keys_str:
            # Try single key
            single_key = os.getenv('GOOGLE_API_KEY', '')
            return [single_key] if single_key else []
        return [k.strip() for k in keys_str.split(',') if k.strip()]

    def _load_prompting_guide(self, data_dir: Path) -> str:
        """Load the NanoBanana Pro prompting guide."""
        guide_path = data_dir / 'prompting_guide.md'
        if guide_path.exists():
            return guide_path.read_text()
        return ""
