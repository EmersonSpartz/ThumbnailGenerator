"""
Favorites System - Track successful thumbnails and learn from them.

This module allows you to:
1. Mark thumbnails as favorites/winners
2. Store metadata about what made them successful
3. Use favorites to guide future generation
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from threading import Lock
from typing import Optional


class FavoritesManager:
    """Manage favorite/winning thumbnails and learn from them."""

    def __init__(self, settings):
        self.settings = settings
        self.favorites_path = settings.favorites_db_path
        self._lock = Lock()
        self.favorites = self._load_favorites()

    def _load_favorites(self) -> dict:
        """Load favorites from disk."""
        if self.favorites_path.exists():
            try:
                return json.loads(self.favorites_path.read_text())
            except json.JSONDecodeError:
                return {"favorites": [], "patterns": {}}
        return {"favorites": [], "patterns": {}}

    def _save_favorites(self):
        """Save favorites to disk atomically (write to temp, fsync, then rename)."""
        self.favorites_path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self.favorites_path.parent), suffix='.tmp', prefix='favorites_'
            )
            tmp_path = Path(tmp_path_str)
            with os.fdopen(fd, 'w') as f:
                fd = None  # os.fdopen takes ownership of fd
                json.dump(self.favorites, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.favorites_path)
        except Exception as e:
            print(f"[FAVORITES] Error saving favorites: {e}")
            if fd is not None:
                os.close(fd)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def add_favorite(
        self,
        thumbnail_path: str,
        concept_name: str,
        prompt: str,
        title_ref: str = "",
        category: str = "",
        description: str = "",
        notes: str = "",
        performance_data: Optional[dict] = None
    ) -> dict:
        """
        Add a thumbnail to favorites.

        Args:
            thumbnail_path: Path to the thumbnail image
            concept_name: The concept name used to generate it
            prompt: The full prompt used for image generation
            title_ref: Which video title this was for
            category: The category/theme
            description: Description of the concept
            notes: User notes about why this worked
            performance_data: Optional dict with CTR, views, etc.

        Returns:
            The created favorite entry
        """
        with self._lock:
            favorite = {
                "id": len(self.favorites["favorites"]) + 1,
                "thumbnail_path": thumbnail_path,
                "concept_name": concept_name,
                "prompt": prompt,
                "title_ref": title_ref,
                "category": category,
                "description": description,
                "notes": notes,
                "performance_data": performance_data or {},
                "added_at": datetime.now().isoformat(),
            }

            self.favorites["favorites"].append(favorite)
            self._update_patterns(favorite)
            self._save_favorites()

            return favorite

    def remove_favorite(self, favorite_id: int) -> bool:
        """Remove a favorite by ID."""
        with self._lock:
            original_len = len(self.favorites["favorites"])
            self.favorites["favorites"] = [
                f for f in self.favorites["favorites"] if f["id"] != favorite_id
            ]
            if len(self.favorites["favorites"]) < original_len:
                self._save_favorites()
                return True
            return False

    def get_all_favorites(self) -> list:
        """Get all favorites."""
        with self._lock:
            return list(self.favorites["favorites"])

    def get_favorites_by_category(self, category: str) -> list:
        """Get favorites filtered by category."""
        with self._lock:
            return [
                f for f in self.favorites["favorites"]
                if f.get("category", "").lower() == category.lower()
            ]

    def _update_patterns(self, favorite: dict):
        """
        Analyze the favorite and update pattern tracking.
        This helps identify what elements lead to success.
        """
        patterns = self.favorites.get("patterns", {})

        # Track category success
        category = favorite.get("category", "Unknown")
        if category not in patterns:
            patterns[category] = {"count": 0, "concepts": []}
        patterns[category]["count"] += 1
        patterns[category]["concepts"].append(favorite["concept_name"])

        self.favorites["patterns"] = patterns

    def get_success_patterns(self) -> dict:
        """
        Get analyzed patterns from successful thumbnails.
        Returns insights about what categories/concepts work well.
        """
        with self._lock:
            return dict(self.favorites.get("patterns", {}))

    def get_favorites_summary_for_prompt(self, limit: int = 5) -> str:
        """
        Generate a summary of favorites to include in Claude's prompt.
        This helps Claude understand what kinds of thumbnails have worked.
        """
        with self._lock:
            favorites = list(self.favorites["favorites"][-limit:])  # Get most recent
            patterns = dict(self.favorites.get("patterns", {}))

        if not favorites:
            return ""

        summary_parts = ["## SUCCESSFUL THUMBNAIL EXAMPLES\n"]
        summary_parts.append("These thumbnails have performed well. Generate concepts with similar qualities:\n")

        for fav in favorites:
            summary_parts.append(f"""
### {fav['concept_name']}
- Category: {fav.get('category', 'Unknown')}
- Description: {fav.get('description', 'N/A')}
- Why it worked: {fav.get('notes', 'Not specified')}
""")

        # Add pattern insights (patterns already captured under lock above)
        if patterns:
            summary_parts.append("\n### Success Patterns:")
            top_categories = sorted(
                patterns.items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )[:3]
            for cat, data in top_categories:
                summary_parts.append(f"- {cat}: {data['count']} successful thumbnails")

        return "\n".join(summary_parts)

    def get_favorite_for_variation(self, favorite_id: int) -> Optional[dict]:
        """Get a specific favorite to use as basis for variations."""
        with self._lock:
            for fav in self.favorites["favorites"]:
                if fav["id"] == favorite_id:
                    return dict(fav)
            return None


class PerformanceTracker:
    """
    Track thumbnail performance from YouTube Analytics.
    This is optional but powerful if connected to real data.
    """

    def __init__(self, settings):
        self.settings = settings
        self.performance_path = settings.data_dir / 'performance.json'
        self._lock = Lock()
        self.performance_data = self._load_performance()

    def _load_performance(self) -> dict:
        """Load performance data."""
        if self.performance_path.exists():
            try:
                return json.loads(self.performance_path.read_text())
            except json.JSONDecodeError:
                return {"thumbnails": {}}
        return {"thumbnails": {}}

    def _save_performance(self):
        """Save performance data atomically (write to temp, fsync, then rename)."""
        self.performance_path.parent.mkdir(parents=True, exist_ok=True)
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self.performance_path.parent), suffix='.tmp', prefix='performance_'
            )
            tmp_path = Path(tmp_path_str)
            with os.fdopen(fd, 'w') as f:
                fd = None
                json.dump(self.performance_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.performance_path)
        except Exception as e:
            print(f"[PERFORMANCE] Error saving performance: {e}")
            if fd is not None:
                os.close(fd)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def record_performance(
        self,
        thumbnail_path: str,
        ctr: float = 0.0,
        impressions: int = 0,
        clicks: int = 0,
        video_id: str = ""
    ):
        """Record performance metrics for a thumbnail."""
        with self._lock:
            self.performance_data["thumbnails"][thumbnail_path] = {
                "ctr": ctr,
                "impressions": impressions,
                "clicks": clicks,
                "video_id": video_id,
                "recorded_at": datetime.now().isoformat()
            }
            self._save_performance()

    def get_top_performers(self, metric: str = "ctr", limit: int = 10) -> list:
        """Get top performing thumbnails by a metric."""
        with self._lock:
            thumbnails = dict(self.performance_data.get("thumbnails", {}))
        sorted_thumbs = sorted(
            thumbnails.items(),
            key=lambda x: x[1].get(metric, 0),
            reverse=True
        )
        return sorted_thumbs[:limit]
