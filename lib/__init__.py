"""Thumbnail Generator Library Modules."""

from .config import Settings
from .claude_client import ClaudeIdeator
from .image_generator import (
    GeminiImageGenerator,
    ReplicateImageGenerator,
    IdeogramGenerator,
    PikzelsGenerator,
    GPTImageGenerator,
    RecraftGenerator,
    TogetherFluxGenerator,
    MultiModelGenerator
)
from .favorites import FavoritesManager, PerformanceTracker
from .freshness import FreshnessTracker
from .text_overlay import TextOverlay
from .refiner import ThumbnailRefiner, IterationSession
from .multi_ideator import MultiLLMIdeator, ClaudeIdeatorV2, ChatGPTIdeator, GeminiIdeator
from .job_manager import JobManager, job_manager
from .prompt_manager import PromptManager
from .agentic_refiner import AgenticImageRefiner
from .template_engine import TemplateCompositor, get_template_info, get_claude_instruction
from .job_store import JobEventStore, job_event_store

__all__ = [
    'Settings',
    'ClaudeIdeator',
    'ClaudeIdeatorV2',
    'ChatGPTIdeator',
    'GeminiIdeator',
    'MultiLLMIdeator',
    'GeminiImageGenerator',
    'ReplicateImageGenerator',
    'IdeogramGenerator',
    'PikzelsGenerator',
    'GPTImageGenerator',
    'RecraftGenerator',
    'TogetherFluxGenerator',
    'MultiModelGenerator',
    'FavoritesManager',
    'PerformanceTracker',
    'FreshnessTracker',
    'TextOverlay',
    'ThumbnailRefiner',
    'IterationSession',
    'JobManager',
    'job_manager',
    'PromptManager',
    'AgenticImageRefiner',
]
