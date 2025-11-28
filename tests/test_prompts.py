"""Tests for grind.prompts module."""

import pytest
from grind.prompts import GRIND_PROMPT, CONTINUE_PROMPT, DECOMPOSE_PROMPT, build_prompt
from grind.models import PromptConfig


class TestPromptConstants:
    def test_grind_prompt_has_placeholders(self):
        assert "{task}" in GRIND_PROMPT
        assert "{verify_cmd}" in GRIND_PROMPT
        assert "GRIND_COMPLETE" in GRIND_PROMPT
        assert "GRIND_STUCK" in GRIND_PROMPT

    def test_continue_prompt_exists(self):
        assert "Continue" in CONTINUE_PROMPT
        assert "GRIND_COMPLETE" in CONTINUE_PROMPT

    def test_decompose_prompt_has_placeholders(self):
        assert "{problem}" in DECOMPOSE_PROMPT
        assert "{verify_cmd}" in DECOMPOSE_PROMPT


class TestBuildPrompt:
    def test_default_prompt(self):
        config = PromptConfig()
        result = build_prompt(config, "Fix tests", "pytest")

        assert "Fix tests" in result
        assert "pytest" in result
        assert "GRIND_COMPLETE" in result

    def test_custom_prompt(self):
        config = PromptConfig(
            custom_prompt="Custom: {task} | {verify_cmd}"
        )
        result = build_prompt(config, "Fix tests", "pytest")

        assert result == "Custom: Fix tests | pytest"
        assert "GRIND_COMPLETE" not in result

    def test_with_preamble(self):
        config = PromptConfig(
            preamble="You are an expert."
        )
        result = build_prompt(config, "Fix tests", "pytest")

        assert result.startswith("You are an expert.")
        assert "Fix tests" in result
        assert "pytest" in result

    def test_with_additional_context(self):
        config = PromptConfig(
            additional_context="Database: PostgreSQL"
        )
        result = build_prompt(config, "Fix tests", "pytest")

        assert "ADDITIONAL CONTEXT" in result
        assert "Database: PostgreSQL" in result

    def test_with_additional_rules(self):
        config = PromptConfig(
            additional_rules=["Rule 1", "Rule 2", "Rule 3"]
        )
        result = build_prompt(config, "Fix tests", "pytest")

        assert "ADDITIONAL RULES" in result
        assert "- Rule 1" in result
        assert "- Rule 2" in result
        assert "- Rule 3" in result

    def test_with_all_options(self):
        config = PromptConfig(
            preamble="You are an expert.",
            additional_rules=["Be careful", "Test everything"],
            additional_context="Python 3.11"
        )
        result = build_prompt(config, "Fix bugs", "pytest -v")

        assert "You are an expert." in result
        assert "Fix bugs" in result
        assert "pytest -v" in result
        assert "ADDITIONAL CONTEXT" in result
        assert "Python 3.11" in result
        assert "ADDITIONAL RULES" in result
        assert "- Be careful" in result
        assert "- Test everything" in result

    def test_empty_config_uses_default(self):
        config = PromptConfig()
        result = build_prompt(config, "Fix tests", "pytest")

        assert "GRIND_COMPLETE" in result
        assert "GRIND_STUCK" in result
        assert "Fix tests" in result
        assert "pytest" in result
