"""
Freshness Tracker - Avoid generating duplicate or similar concepts.

Tracks:
- Previously used concept names
- Categories to ensure variety
- Similarity detection
"""

import json
from pathlib import Path
from collections import Counter
from typing import Optional


class FreshnessTracker:
    """Track used ideas to maintain freshness and variety."""

    def __init__(self, settings):
        self.settings = settings
        self.tracker_path = settings.data_dir / 'freshness_tracker.json'
        self.data = self._load_data()

    def _load_data(self) -> dict:
        """Load tracking data from disk."""
        if self.tracker_path.exists():
            try:
                return json.loads(self.tracker_path.read_text())
            except json.JSONDecodeError:
                return self._empty_data()
        return self._empty_data()

    def _empty_data(self) -> dict:
        return {
            "used_ideas": [],
            "category_counts": {},
            "concept_summaries": []
        }

    def _save_data(self):
        """Save tracking data to disk."""
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        self.tracker_path.write_text(json.dumps(self.data, indent=2))

    def add_used_idea(self, concept: dict):
        """Record a concept as used."""
        concept_name = concept.get('concept_name', '')
        category = concept.get('category', 'Unknown')
        description = concept.get('description', '')

        if concept_name and concept_name not in self.data["used_ideas"]:
            self.data["used_ideas"].append(concept_name)

        # Track category
        if category not in self.data["category_counts"]:
            self.data["category_counts"][category] = 0
        self.data["category_counts"][category] += 1

        # Store summary for similarity checking
        self.data["concept_summaries"].append({
            "name": concept_name,
            "category": category,
            "description": description[:200]  # Truncate for storage
        })

        self._save_data()

    def get_summary_list(self) -> list[str]:
        """Get list of used idea names for passing to Claude."""
        return self.data["used_ideas"]

    def filter_fresh(self, concepts: list[dict]) -> list[dict]:
        """
        Filter out concepts that are too similar to previously used ones.

        Returns only concepts that pass the freshness check.
        """
        used_names = set(name.lower() for name in self.data["used_ideas"])
        fresh = []

        for concept in concepts:
            name = concept.get('concept_name', '').lower()

            # Check exact match
            if name in used_names:
                continue

            # Check similarity (simple word overlap)
            name_words = set(name.split())
            is_similar = False
            for used in used_names:
                used_words = set(used.split())
                overlap = len(name_words & used_words)
                if overlap >= 2 and overlap / max(len(name_words), 1) > 0.5:
                    is_similar = True
                    break

            if not is_similar:
                fresh.append(concept)

        return fresh

    def get_category_stats(self) -> dict:
        """Get statistics about category distribution."""
        counts = self.data.get("category_counts", {})
        total = sum(counts.values()) or 1

        stats = {
            "counts": counts,
            "percentages": {cat: count/total*100 for cat, count in counts.items()},
            "total": total,
            "imbalanced": False
        }

        # Check if any category is severely over/underrepresented
        if counts:
            avg = total / len(counts)
            max_count = max(counts.values())
            min_count = min(counts.values())
            if max_count > avg * 2 or min_count < avg * 0.3:
                stats["imbalanced"] = True

        return stats

    def get_underrepresented_categories(self) -> list[str]:
        """Get categories that are underrepresented."""
        counts = self.data.get("category_counts", {})
        if not counts:
            return []

        total = sum(counts.values())
        avg = total / len(counts)

        return [cat for cat, count in counts.items() if count < avg * 0.5]

    def clear(self):
        """Clear all tracking data (start fresh)."""
        self.data = self._empty_data()
        self._save_data()

    def get_recent_concepts(self, limit: int = 20) -> list[dict]:
        """Get the most recent concepts."""
        return self.data.get("concept_summaries", [])[-limit:]
