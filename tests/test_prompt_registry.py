"""Tests for PromptRegistry — Jinja2-based prompt template management."""

from __future__ import annotations

from pathlib import Path

import pytest

from finer.prompts.registry import PromptRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> PromptRegistry:
    """PromptRegistry using the actual prompts directory."""
    return PromptRegistry()


@pytest.fixture()
def tmp_prompts_dir(tmp_path: Path) -> Path:
    """A temporary prompts directory with test templates."""
    d = tmp_path / "prompts"
    d.mkdir()

    # Simple template
    (d / "test" / "hello.j2").parent.mkdir()
    (d / "test" / "hello.j2").write_text("Hello, {{ name }}!")

    # Template with frontmatter-like comment
    (d / "test" / "system.j2").write_text(
        "You are a {{ role }} assistant.\nFollow these rules:\n{% for rule in rules %}\n- {{ rule }}\n{% endfor %}"
    )

    return d


@pytest.fixture()
def tmp_registry(tmp_prompts_dir: Path) -> PromptRegistry:
    """PromptRegistry using the temporary prompts directory."""
    return PromptRegistry(prompts_dir=tmp_prompts_dir)


# ---------------------------------------------------------------------------
# Rendering tests
# ---------------------------------------------------------------------------


class TestPromptRegistryRender:
    def test_render_simple_template(self, tmp_registry: PromptRegistry):
        result = tmp_registry.render("test/hello", name="World")
        assert result == "Hello, World!"

    def test_render_auto_appends_j2(self, tmp_registry: PromptRegistry):
        result = tmp_registry.render("test/hello", name="Finer")
        assert result == "Hello, Finer!"

    def test_render_with_j2_extension(self, tmp_registry: PromptRegistry):
        result = tmp_registry.render("test/hello.j2", name="Test")
        assert result == "Hello, Test!"

    def test_render_with_loop(self, tmp_registry: PromptRegistry):
        result = tmp_registry.render(
            "test/system",
            role="helpful",
            rules=["Be concise", "Be accurate"],
        )
        assert "helpful" in result
        assert "- Be concise" in result
        assert "- Be accurate" in result

    def test_render_nonexistent_template_raises(self, tmp_registry: PromptRegistry):
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            tmp_registry.render("nonexistent/template")

    def test_render_f3_system_prompt(self, registry: PromptRegistry):
        """Verify the actual F3 system template renders without error."""
        result = registry.render("f3_intent_extraction/system")
        assert "F3 Investment Intent Extractor" in result
        assert "NormalizedInvestmentIntent" in result

    def test_render_f3_user_prompt(self, registry: PromptRegistry):
        """Verify the actual F3 user template renders with all variables."""
        result = registry.render(
            "f3_intent_extraction/user",
            content_text="看好新能源",
            creator_name="TestKOL",
            creator_id="kol_001",
            source_type="feishu_chat",
            published_at="2026-01-15T10:00:00Z",
            known_entities="  - 宁德时代\n  - 比亚迪",
        )
        assert "看好新能源" in result
        assert "TestKOL" in result
        assert "kol_001" in result
        assert "feishu_chat" in result
        assert "2026-01-15T10:00:00Z" in result
        assert "宁德时代" in result


# ---------------------------------------------------------------------------
# Listing and discovery tests
# ---------------------------------------------------------------------------


class TestPromptRegistryList:
    def test_list_templates(self, tmp_registry: PromptRegistry):
        templates = tmp_registry.list_templates()
        assert "test/hello" in templates
        assert "test/system" in templates

    def test_has_template_true(self, tmp_registry: PromptRegistry):
        assert tmp_registry.has_template("test/hello") is True

    def test_has_template_false(self, tmp_registry: PromptRegistry):
        assert tmp_registry.has_template("nonexistent") is False

    def test_list_actual_templates(self, registry: PromptRegistry):
        """Verify F3 templates are discoverable in the actual prompts dir."""
        templates = registry.list_templates()
        assert any("f3_intent_extraction" in t for t in templates)


# ---------------------------------------------------------------------------
# Directory tests
# ---------------------------------------------------------------------------


class TestPromptRegistryDir:
    def test_default_prompts_dir(self):
        registry = PromptRegistry()
        assert registry.prompts_dir.exists()
        assert registry.prompts_dir.name == "prompts"

    def test_custom_prompts_dir(self, tmp_path: Path):
        custom = tmp_path / "my_prompts"
        custom.mkdir()
        registry = PromptRegistry(prompts_dir=custom)
        assert registry.prompts_dir == custom
