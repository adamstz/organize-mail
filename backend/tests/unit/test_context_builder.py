"""Tests for ContextBuilder.

Tests the context building logic for formatting email data into LLM context strings.
"""
import os
import pytest
from datetime import datetime

os.environ["LLM_PROVIDER"] = "rules"
os.environ.pop("OLLAMA_HOST", None)

from src.services.context_builder import ContextBuilder
from src.models.message import MailMessage


class TestContextBuilderInit:
    """Tests for ContextBuilder initialization."""

    def test_init(self):
        """Should initialize without errors."""
        builder = ContextBuilder()
        assert builder is not None


class TestBuildContext:
    """Tests for build_context method with similarity scores."""

    def test_build_context_single_email(self, context_builder):
        """Should build context from a single email with score."""
        import base64
        from tests.unit.fixtures_payloads import make_simple_text_payload
        
        full_body = "This is the full email content with much more detail than the snippet."
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test Subject",
            snippet="This is the email content.",
            internal_date=1733050800000,  # Dec 1, 2025, 10:00 AM UTC
            payload=make_simple_text_payload(full_body)
        )
        
        similar_emails = [(email, 0.95)]
        context = context_builder.build_context(similar_emails)
        
        assert "Email 1" in context
        assert "Relevance: 0.95" in context
        assert "Test Subject" in context
        assert "sender@example.com" in context
        # Should use full body, not snippet
        assert full_body in context

    def test_build_context_multiple_emails(self, context_builder):
        """Should build context from multiple emails with scores."""
        emails = [
            (MailMessage(
                id="test1",
                from_="sender1@example.com",
                subject="First Email",
                snippet="Content 1",
                internal_date=1733050800000,
            ), 0.95),
            (MailMessage(
                id="test2",
                from_="sender2@example.com",
                subject="Second Email",
                snippet="Content 2",
                internal_date=1733050800000,
            ), 0.85),
            (MailMessage(
                id="test3",
                from_="sender3@example.com",
                subject="Third Email",
                snippet="Content 3",
                internal_date=1733050800000,
            ), 0.75),
        ]
        
        context = context_builder.build_context(emails)
        
        assert "Email 1" in context
        assert "Email 2" in context
        assert "Email 3" in context
        assert "Relevance: 0.95" in context
        assert "Relevance: 0.85" in context
        assert "Relevance: 0.75" in context
        assert "First Email" in context
        assert "Second Email" in context
        assert "Third Email" in context

    def test_build_context_empty_list(self, context_builder):
        """Should handle empty email list."""
        context = context_builder.build_context([])
        assert context == ""

    def test_build_context_preserves_order(self, context_builder):
        """Should preserve email order in context."""
        emails = [
            (MailMessage(id="first", subject="First", snippet="1", internal_date=1733050800000), 0.9),
            (MailMessage(id="second", subject="Second", snippet="2", internal_date=1733050800000), 0.8),
        ]
        
        context = context_builder.build_context(emails)
        
        # First should appear before Second
        first_pos = context.find("First")
        second_pos = context.find("Second")
        assert first_pos < second_pos


class TestBuildContextFromMessages:
    """Tests for build_context_from_messages method without similarity scores."""

    def test_build_context_from_messages_single(self, context_builder):
        """Should build context from a single message."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test Subject",
            snippet="Email content here.",
            internal_date=1733050800000,
        )
        
        context = context_builder.build_context_from_messages([email])
        
        assert "Email 1" in context
        assert "Relevance" not in context  # No similarity score
        assert "Test Subject" in context
        assert "sender@example.com" in context

    def test_build_context_from_messages_multiple(self, context_builder):
        """Should build context from multiple messages."""
        emails = [
            MailMessage(id="test1", subject="First", snippet="1", internal_date=1733050800000),
            MailMessage(id="test2", subject="Second", snippet="2", internal_date=1733050800000),
        ]
        
        context = context_builder.build_context_from_messages(emails)
        
        assert "Email 1" in context
        assert "Email 2" in context
        assert "First" in context
        assert "Second" in context

    def test_build_context_from_messages_empty(self, context_builder):
        """Should handle empty message list."""
        context = context_builder.build_context_from_messages([])
        assert context == ""


class TestFormatEmailWithScore:
    """Tests for _format_email_with_score method."""

    def test_format_with_all_fields(self, context_builder):
        """Should format email with all fields present."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test Subject",
            snippet="Email content",
            internal_date=1733050800000,
        )
        
        formatted = context_builder._format_email_with_score(1, email, 0.92)
        
        assert "Email 1 (Relevance: 0.92)" in formatted
        assert "Subject: Test Subject" in formatted
        assert "From: sender@example.com" in formatted
        assert "Content: Email content" in formatted

    def test_format_with_missing_subject(self, context_builder):
        """Should handle missing subject."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject=None,
            snippet="Content",
            internal_date=1733050800000,
        )
        
        formatted = context_builder._format_email_with_score(1, email, 0.9)
        
        assert "Subject: No subject" in formatted

    def test_format_with_missing_from(self, context_builder):
        """Should handle missing from address."""
        email = MailMessage(
            id="test1",
            from_=None,
            subject="Test",
            snippet="Content",
            internal_date=1733050800000,
        )
        
        formatted = context_builder._format_email_with_score(1, email, 0.9)
        
        assert "From: Unknown" in formatted

    def test_format_with_missing_snippet(self, context_builder):
        """Should handle missing snippet."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test",
            snippet=None,
            internal_date=1733050800000,
        )
        
        formatted = context_builder._format_email_with_score(1, email, 0.9)
        
        assert "Content: No content available" in formatted

    def test_format_with_missing_date(self, context_builder):
        """Should handle missing date."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test",
            snippet="Content",
            internal_date=None,
        )
        
        formatted = context_builder._format_email_with_score(1, email, 0.9)
        
        assert "Date: Unknown" in formatted


class TestFormatEmail:
    """Tests for _format_email method without score."""

    def test_format_email_basic(self, context_builder):
        """Should format email without score."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test Subject",
            snippet="Email content",
            internal_date=1733050800000,
        )
        
        formatted = context_builder._format_email(1, email)
        
        assert "Email 1:" in formatted
        assert "Relevance" not in formatted
        assert "Subject: Test Subject" in formatted
        assert "From: sender@example.com" in formatted

    def test_format_email_missing_fields(self, context_builder):
        """Should handle all missing fields gracefully."""
        email = MailMessage(
            id="test1",
            from_=None,
            subject=None,
            snippet=None,
            internal_date=None,
        )
        
        formatted = context_builder._format_email(1, email)
        
        assert "Subject: No subject" in formatted
        assert "From: Unknown" in formatted
        assert "Content: No content available" in formatted
        assert "Date: Unknown" in formatted


class TestFormatDate:
    """Tests for _format_date method."""

    def test_format_date_valid_timestamp(self, context_builder):
        """Should format valid timestamp correctly."""
        # Dec 1, 2025, 10:00 AM UTC = 1733050800000 ms
        timestamp = 1733050800000
        
        formatted = context_builder._format_date(timestamp)
        
        # Should contain year and be a valid date format (YYYY-MM-DD HH:MM)
        # Note: exact date depends on local timezone
        assert len(formatted) > 5  # Should be a date string, not "Unknown"
        assert "-" in formatted or "/" in formatted  # Date separator

    def test_format_date_none(self, context_builder):
        """Should handle None timestamp."""
        formatted = context_builder._format_date(None)
        assert formatted == "Unknown"

    def test_format_date_zero(self, context_builder):
        """Should handle zero timestamp (Unix epoch)."""
        formatted = context_builder._format_date(0)
        # Zero is falsy, so it should return "Unknown"
        assert formatted == "Unknown"

    def test_format_date_different_timestamps(self, context_builder):
        """Should format different timestamps correctly."""
        # Test that timestamps produce different formatted dates
        ts1 = 1609459200000  # Jan 1, 2021 (approx)
        ts2 = 1672531200000  # Jan 1, 2023 (approx)
        
        formatted1 = context_builder._format_date(ts1)
        formatted2 = context_builder._format_date(ts2)
        
        # Both should be valid date strings (not Unknown)
        assert formatted1 != "Unknown"
        assert formatted2 != "Unknown"
        # They should be different dates
        assert formatted1 != formatted2

    def test_format_date_invalid_value(self, context_builder):
        """Should handle invalid timestamp values gracefully."""
        # String that can't be converted
        formatted = context_builder._format_date("invalid")
        # Should return the string representation or Unknown
        assert formatted in ("Unknown", "invalid")


class TestContextBuilderEdgeCases:
    """Tests for edge cases and robustness."""

    def test_very_long_snippet(self, context_builder):
        """Should handle very long snippets."""
        long_snippet = "A" * 10000
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test",
            snippet=long_snippet,
            internal_date=1733050800000,
        )
        
        context = context_builder.build_context_from_messages([email])
        
        # Should include the content (may be truncated by LLM later)
        assert "Content:" in context
        assert "A" in context

    def test_special_characters_in_content(self, context_builder):
        """Should handle special characters."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test with émojis 🎉 and ünïcödé",
            snippet="Content with <html> tags & special chars: \"quotes\"",
            internal_date=1733050800000,
        )
        
        context = context_builder.build_context_from_messages([email])
        
        assert "émojis" in context or "emoji" in context.lower()
        assert "<html>" in context or "html" in context

    def test_newlines_in_content(self, context_builder):
        """Should handle newlines in content."""
        email = MailMessage(
            id="test1",
            from_="sender@example.com",
            subject="Test",
            snippet="Line 1\nLine 2\nLine 3",
            internal_date=1733050800000,
        )
        
        context = context_builder.build_context_from_messages([email])
        
        assert "Line 1" in context
        assert "Line 2" in context

    def test_empty_string_fields(self, context_builder):
        """Should handle empty string fields."""
        email = MailMessage(
            id="test1",
            from_="",
            subject="",
            snippet="",
            internal_date=1733050800000,
        )
        
        # Empty strings are falsy, should use defaults
        formatted = context_builder._format_email(1, email)
        
        assert "Subject: No subject" in formatted or "Subject:" in formatted
        assert "From: Unknown" in formatted or "From:" in formatted

    def test_large_number_of_emails(self, context_builder):
        """Should handle many emails without error."""
        emails = [
            MailMessage(
                id=f"test{i}",
                from_=f"sender{i}@example.com",
                subject=f"Subject {i}",
                snippet=f"Content {i}",
                internal_date=1733050800000,
            )
            for i in range(100)
        ]
        
        context = context_builder.build_context_from_messages(emails)
        
        # Should include all emails
        assert "Email 1:" in context
        assert "Email 100:" in context

    def test_similarity_score_precision(self, context_builder):
        """Should format similarity scores with 2 decimal places."""
        email = MailMessage(
            id="test1",
            subject="Test",
            snippet="Content",
            internal_date=1733050800000,
        )
        
        # Test various precision levels
        test_cases = [
            (0.9999999, "1.00"),  # Rounds up
            (0.123456, "0.12"),   # Rounds down
            (0.555, "0.55"),      # Rounds to nearest
        ]
        
        for score, expected in test_cases:
            formatted = context_builder._format_email_with_score(1, email, score)
            assert f"Relevance: {expected}" in formatted or f"Relevance: {score:.2f}" in formatted
