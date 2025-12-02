"""Tests for LLM processor classification logic.

Note: These tests focus on rule-based classification, provider detection,
prompt building, and response parsing. They do NOT test actual API calls
to external LLM providers (OpenAI, Anthropic, Ollama) as those would
require real API keys or running services.
"""

import os
import json
import pytest
from src.services import LLMProcessor
from src.services.prompt_templates import CLASSIFICATION_SYSTEM_MESSAGE, build_classification_prompt


class TestLLMProcessorConstants:
    """Test shared configuration constants."""

    def test_constants_are_set(self):
        """Verify all shared constants exist and have reasonable values."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        
        # Check system message from llm_prompts module
        assert CLASSIFICATION_SYSTEM_MESSAGE is not None
        assert len(CLASSIFICATION_SYSTEM_MESSAGE) > 0
        assert "classification" in CLASSIFICATION_SYSTEM_MESSAGE.lower()
        
        assert processor.TEMPERATURE == 0.3
        assert processor.MAX_TOKENS == 200
        assert processor.TIMEOUT == 60  # Updated timeout
        
        os.environ.pop("LLM_PROVIDER", None)


class TestProviderDetection:
    """Test auto-detection of LLM providers."""

    def test_explicit_provider_rules(self):
        """LLM_PROVIDER=rules should use rule-based."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        assert processor.provider == "rules"
        os.environ.pop("LLM_PROVIDER", None)

    def test_explicit_provider_openai(self):
        """LLM_PROVIDER=openai should set provider even without API key."""
        os.environ["LLM_PROVIDER"] = "openai"
        processor = LLMProcessor()
        assert processor.provider == "openai"
        os.environ.pop("LLM_PROVIDER", None)

    def test_raises_error_when_nothing_available(self, monkeypatch):
        """Should raise error when no providers detected and not explicitly rules."""
        # Clear all provider-related env vars
        for key in ["LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ORGANIZE_MAIL_LLM_CMD"]:
            os.environ.pop(key, None)
        
        # Mock _is_ollama_running to return False
        def fake_ollama_check(self):
            return False
        monkeypatch.setattr(LLMProcessor, "_is_ollama_running", fake_ollama_check)
        
        with pytest.raises(RuntimeError, match="No LLM provider configured"):
            LLMProcessor()
    
    def test_explicit_rules_provider_works(self):
        """LLM_PROVIDER=rules should work for testing."""
        # Clear all other providers
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ORGANIZE_MAIL_LLM_CMD"]:
            os.environ.pop(key, None)
        
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        assert processor.provider == "rules"
        os.environ.pop("LLM_PROVIDER", None)


class TestModelNameSelection:
    """Test model name selection logic."""

    def test_explicit_model_name(self):
        """LLM_MODEL env var should override defaults."""
        os.environ["LLM_MODEL"] = "my-custom-model"
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        assert processor.model == "my-custom-model"
        os.environ.pop("LLM_MODEL", None)
        os.environ.pop("LLM_PROVIDER", None)

    def test_default_model_for_openai(self):
        """OpenAI provider should default to gpt-3.5-turbo."""
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ.pop("LLM_MODEL", None)
        processor = LLMProcessor()
        assert processor.model == "gpt-3.5-turbo"
        os.environ.pop("LLM_PROVIDER", None)

    def test_default_model_for_ollama(self):
        """Ollama provider should default to llama3."""
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ.pop("LLM_MODEL", None)
        processor = LLMProcessor()
        assert processor.model == "llama3"
        os.environ.pop("LLM_PROVIDER", None)


class TestPromptBuilding:
    """Test classification prompt construction."""

    def test_prompt_includes_subject_and_body(self):
        """Prompt should contain email subject and body."""
        prompt = build_classification_prompt(
            "Invoice Payment Due",
            "Please pay your invoice for $500."
        )
        
        assert "Invoice Payment Due" in prompt
        assert "Please pay your invoice" in prompt

    def test_prompt_includes_instructions(self):
        """Prompt should include classification instructions."""
        prompt = build_classification_prompt("Test", "Test body")
        
        assert "labels" in prompt.lower()
        assert "priority" in prompt.lower()
        assert "json" in prompt.lower()

    def test_prompt_truncates_long_body(self):
        """Long email bodies should be truncated to avoid token limits."""
        long_body = "x" * 5000  # 5000 characters
        prompt = build_classification_prompt("Test", long_body)
        
        # Body should be truncated to 2000 chars max
        # Prompt is longer now due to expanded label list (~1300 chars)
        assert len(prompt) < 3500  # Prompt + truncated body


class TestResponseParsing:
    """Test parsing of LLM responses with various formats."""

    def test_parse_valid_json(self):
        """Should parse valid JSON response."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"labels": ["finance", "work"], "priority": "high", "summary": "Invoice payment due"}'
        result = processor._parse_llm_response(response)
        
        assert result["labels"] == ["finance", "work"]
        assert result["priority"] == "high"
        assert result["summary"] == "Invoice payment due"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_json_with_markdown_backticks(self):
        """Should extract JSON from markdown code blocks."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '```json\n{"labels": ["security"], "priority": "normal", "summary": "Security alert"}\n```'
        result = processor._parse_llm_response(response)
        
        assert result["labels"] == ["security"]
        assert result["priority"] == "normal"
        assert result["summary"] == "Security alert"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_singular_label_field(self):
        """Should handle 'label' (singular) and convert to 'labels' (plural)."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"label": "finance", "priority": "high"}'
        result = processor._parse_llm_response(response)
        
        assert "labels" in result
        assert result["labels"] == ["finance"]
        assert "label" not in result
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_comma_separated_labels(self):
        """Should handle comma-separated label strings."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"label": "finance,work,security", "priority": "high"}'
        result = processor._parse_llm_response(response)
        
        assert result["labels"] == ["finance", "work", "security"]
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_missing_priority_defaults_to_normal(self):
        """Should default to 'normal' priority if missing."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"labels": ["finance"], "summary": "Test"}'
        result = processor._parse_llm_response(response)
        
        assert result["priority"] == "normal"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_missing_summary_defaults_to_empty(self):
        """Should default to empty string if summary missing."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"labels": ["finance"], "priority": "high"}'
        result = processor._parse_llm_response(response)
        
        assert result["summary"] == ""
        assert isinstance(result["summary"], str)
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_normalizes_priority_case(self):
        """Should normalize priority to lowercase."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"labels": ["finance"], "priority": "HIGH"}'
        result = processor._parse_llm_response(response)
        
        assert result["priority"] == "high"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_parse_invalid_priority_defaults_to_normal(self):
        """Should default invalid priority values to 'normal'."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        response = '{"labels": ["finance"], "priority": "urgent"}'
        result = processor._parse_llm_response(response)
        
        assert result["priority"] == "normal"
        
        os.environ.pop("LLM_PROVIDER", None)


class TestRuleBasedClassification:
    """Test rule-based classification fallback."""

    def test_finance_keywords(self):
        """Should detect finance-related emails."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        result = processor._rule_based(
            "Invoice #12345",
            "Your payment of $500 is due."
        )
        
        assert "finance" in result["labels"]
        assert "summary" in result
        assert result["summary"] == "Invoice #12345"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_security_keywords(self):
        """Should detect security-related emails and mark as high priority."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        result = processor._rule_based(
            "Security Alert",
            "Unusual login detected on your account."
        )
        
        assert "security" in result["labels"]
        assert result["priority"] == "high"
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_meeting_keywords(self):
        """Should detect meeting-related emails."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        result = processor._rule_based(
            "Team Meeting Tomorrow",
            "Let's schedule a meeting for 3pm."
        )
        
        assert "meetings" in result["labels"]
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_urgent_keywords_set_high_priority(self):
        """Should set high priority for urgent keywords."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        result = processor._rule_based(
            "URGENT: Action Required",
            "Please respond immediately."
        )
        
        assert result["priority"] == "high"
        
        os.environ.pop("LLM_PROVIDER", None)


class TestCategorizeMessage:
    """Test the main categorize_message method."""

    def test_categorize_with_rules_provider(self):
        """Should use rule-based classification when provider is 'rules'."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        
        result = processor.categorize_message(
            "Invoice Payment Due",
            "Your invoice for $500 is overdue."
        )
        
        assert "labels" in result
        assert "priority" in result
        assert "finance" in result["labels"]
        
        os.environ.pop("LLM_PROVIDER", None)

    def test_categorize_returns_dict_with_required_fields(self):
        """Result should always have 'labels', 'priority', and 'summary' fields."""
        os.environ["LLM_PROVIDER"] = "rules"
        processor = LLMProcessor()
        
        result = processor.categorize_message("Test", "Test body")
        
        assert isinstance(result, dict)
        assert "labels" in result
        assert "priority" in result
        assert "summary" in result
        assert isinstance(result["labels"], list)
        assert result["priority"] in ("high", "normal", "low")
        assert isinstance(result["summary"], str)
        
        os.environ.pop("LLM_PROVIDER", None)
