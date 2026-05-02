"""Vision Utils — analyze images using the configured vision model with caching.

Provides a bridge to convert image content into searchable text
for NotebookLM ingestion. Finer OS currently pins vision/OCR to MiMo-V2.5.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from finer.model_config import get_vision_registry

logger = logging.getLogger(__name__)

# Default prompt for image analysis
DEFAULT_PROMPT = """请详细描述这张图片的内容。如果是图表，请分析其中的数据点和结论；如果是截图，请提取其中的文字内容；如果是研究报告页，请总结核心观点。"""


@dataclass
class VisionCache:
    """Cache for vision analysis results to avoid re-processing."""
    cache_dir: Path
    index_file: Path
    index: dict[str, dict[str, Any]]  # file_hash -> cache_entry

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = cache_dir / "vision_cache_index.json"
        self.index = self._load_index()

    def _load_index(self) -> dict:
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self):
        self.index_file.write_text(
            json.dumps(self.index, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file for cache key."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get(self, file_path: Path, prompt: str) -> Optional[str]:
        """Get cached result if available."""
        file_hash = self._compute_file_hash(file_path)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        cache_key = f"{file_hash}_{prompt_hash}"

        if cache_key in self.index:
            entry = self.index[cache_key]
            cache_file = self.cache_dir / entry["cache_file"]
            if cache_file.exists():
                logger.debug(f"Cache hit for {file_path.name}")
                return cache_file.read_text(encoding="utf-8")
        return None

    def set(self, file_path: Path, prompt: str, result: str, model: str) -> str:
        """Cache the analysis result."""
        file_hash = self._compute_file_hash(file_path)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        cache_key = f"{file_hash}_{prompt_hash}"

        # Save result to cache file
        cache_filename = f"{file_hash[:16]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        cache_file = self.cache_dir / cache_filename
        cache_file.write_text(result, encoding="utf-8")

        # Update index
        self.index[cache_key] = {
            "cache_file": cache_filename,
            "original_file": str(file_path),
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "prompt_hash": prompt_hash,
        }
        self._save_index()

        logger.info(f"Cached vision result for {file_path.name}")
        return str(cache_file)


# Global cache instance
_vision_cache: Optional[VisionCache] = None


def get_vision_cache(root: Optional[Path] = None) -> VisionCache:
    """Get or create the global vision cache."""
    global _vision_cache
    if _vision_cache is None and root:
        _vision_cache = VisionCache(root / "data" / "cache" / "vision")
    return _vision_cache


def init_vision_cache(root: Path):
    """Initialize the vision cache."""
    global _vision_cache
    _vision_cache = VisionCache(root / "data" / "cache" / "vision")
    return _vision_cache


class VisionDescriptor:
    """Generates text descriptions for images with MiMo-V2.5 and caching."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "mimo-v2.5",
        root: Path | None = None,
    ):
        self.registry = get_vision_registry()
        self.model = model

        # Initialize cache if root is provided
        self.cache = None
        if root:
            self.cache = init_vision_cache(root)
        elif _vision_cache:
            self.cache = _vision_cache

        # MiMo official examples use MIMO_API_KEY and the api-key HTTP header.
        self.api_key = api_key or os.getenv("MIMO_API_KEY")

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def describe_image(
        self,
        image_path: Path,
        prompt: str = DEFAULT_PROMPT,
        language: str = "zh",
        use_cache: bool = True,
    ) -> str:
        """Get a detailed description of the image content with caching and fallback."""
        # Check cache first
        if use_cache and self.cache:
            cached = self.cache.get(image_path, prompt)
            if cached:
                return cached

        if not image_path.exists():
            return f"Error: File not found at {image_path}"

        registry = get_vision_registry()

        while True:
            if self.api_key:
                model_config = next(
                    (
                        model
                        for model in sorted(registry.models, key=lambda m: m.priority)
                        if model.enabled and model.name not in registry.failed_models
                    ),
                    None,
                )
            else:
                model_config = registry.get_available_model()
            if not model_config:
                return "Error: No available vision models. Please check API keys."

            try:
                # Get API key for this model
                api_key = self.api_key or os.getenv(model_config.api_key_env)
                if not api_key:
                    registry.mark_failed(model_config.name, "No API key")
                    continue

                # Prepare image data
                mime_type = "image/png"
                if image_path.suffix.lower() in (".jpg", ".jpeg"):
                    mime_type = "image/jpeg"

                base64_image = self._encode_image(image_path)

                logger.info(f"Calling {model_config.name} for {image_path.name}")

                # Use httpx with curl User-Agent for proxy compatibility
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "curl/8.0",
                }
                header_value = (
                    f"{model_config.api_key_scheme} {api_key}"
                    if model_config.api_key_scheme
                    else api_key
                )
                headers[model_config.api_key_header] = header_value

                data = {
                    "model": model_config.name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    },
                                },
                            ],
                        }
                    ],
                }
                data[model_config.max_tokens_field] = model_config.max_tokens

                with httpx.Client(timeout=60.0, http2=False) as client:
                    response = client.post(
                        f"{model_config.base_url}/chat/completions",
                        headers=headers,
                        json=data,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]
                        logger.info(f"Successfully generated vision descriptor using {model_config.name}")

                        # Cache the result
                        if self.cache:
                            self.cache.set(image_path, prompt, content, model_config.name)

                        return content
                    else:
                        error_msg = response.text[:200]
                        logger.error(f"Vision API error with {model_config.name}: {error_msg}")

                        # Check if it's a quota/rate limit error
                        if any(x in error_msg.lower() for x in ["quota", "rate", "limit", "exhausted", "insufficient"]):
                            registry.mark_failed(model_config.name, error_msg)
                            continue
                        else:
                            return f"Error: Vision analysis failed. Details: {error_msg}"

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Vision API error with {model_config.name}: {error_msg}")

                # Check if it's a quota/rate limit error
                if any(x in error_msg.lower() for x in ["quota", "rate", "limit", "exhausted", "insufficient"]):
                    registry.mark_failed(model_config.name, error_msg)
                    continue
                else:
                    return f"Error: Vision analysis failed. Details: {e}"


def get_vision_transcript_path(
    root: Path,
    image_path: Path,
    creator_id: str,
) -> Path:
    """Generate a canonical path for the vision sidecar file."""
    transcript_dir = root / "data" / "processed" / "transcripts" / creator_id
    transcript_dir.mkdir(parents=True, exist_ok=True)

    # Use original filename but change extension to .md
    return transcript_dir / f"{image_path.stem}_vision.md"
