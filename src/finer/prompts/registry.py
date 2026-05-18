"""PromptRegistry — Jinja2-based prompt template management.

Loads prompt templates from a directory structure like:
    prompts/
      f3_intent_extraction/
        system.j2
        user.j2
      f5_trade_action/
        system.j2
        user.j2

Templates use Jinja2 syntax with optional YAML frontmatter for metadata
(name, stage, version, model_hint).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

# Default prompts directory: src/finer/prompts/ relative to this file
_DEFAULT_PROMPTS_DIR = Path(__file__).parent


class PromptRegistry:
    """Jinja2-based prompt template registry.

    Usage:
        registry = PromptRegistry()
        rendered = registry.render(
            "f3_intent_extraction/user",
            content_text="...",
            creator_name="...",
        )
    """

    def __init__(self, prompts_dir: Optional[str | Path] = None):
        self._prompts_dir = Path(prompts_dir) if prompts_dir else _DEFAULT_PROMPTS_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._prompts_dir)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def prompts_dir(self) -> Path:
        return self._prompts_dir

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a prompt template with the given variables.

        Args:
            template_name: Dot-separated template path (e.g. "f3_intent_extraction/user").
                           Automatically appends .j2 extension if missing.
            **kwargs: Template variables.

        Returns:
            Rendered prompt string.

        Raises:
            jinja2.TemplateNotFound: If the template does not exist.
        """
        if not template_name.endswith(".j2"):
            template_name = f"{template_name}.j2"

        # Convert dot-separated path to filesystem path
        template_path = template_name.replace(".", "/") if "/" not in template_name else template_name

        template = self._env.get_template(template_path)
        return template.render(**kwargs)

    def list_templates(self) -> list[str]:
        """List all available prompt templates (relative paths without .j2)."""
        templates = []
        for p in self._prompts_dir.rglob("*.j2"):
            rel = p.relative_to(self._prompts_dir)
            templates.append(str(rel.with_suffix("")))
        return sorted(templates)

    def has_template(self, template_name: str) -> bool:
        """Check if a template exists."""
        if not template_name.endswith(".j2"):
            template_name = f"{template_name}.j2"
        template_path = template_name.replace(".", "/") if "/" not in template_name else template_name
        return (self._prompts_dir / template_path).exists()
