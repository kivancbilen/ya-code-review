"""Configuration via environment variables and defaults."""

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    model_config = {"env_prefix": "FB_REVIEW_"}

    anthropic_api_key: str = ""
    model: str = "claude-opus-4-6"
    max_turns: int = 40
    confidence_threshold: float = 0.7
    max_context_tokens: int = 180_000
    chunk_size: int = 30_000  # max chars of diff per review chunk

    # F3: Review memory
    memory_path: str = ""  # default: ~/.fb-review/memory.json

    # F4: Auto-severity calibration
    calibration_enabled: bool = True
    calibration_model: str = "claude-haiku-4-5-20251001"

    def get_api_key(self) -> str:
        import os

        return self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def get_memory_path(self) -> "Path":
        from pathlib import Path

        if self.memory_path:
            return Path(self.memory_path)
        return Path.home() / ".fb-review" / "memory.json"
