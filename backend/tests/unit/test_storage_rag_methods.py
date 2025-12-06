"""Tests for InMemoryStorage RAG-related methods.

Tests the 8 new storage methods added for RAG support:
- search_by_sender()
- search_by_attachment()
- search_by_keywords()
- count_by_topic()
- get_daily_email_stats()
- get_top_senders()
- get_total_message_count()
- get_unread_count()
"""
import os
import pytest

os.environ["LLM_PROVIDER"] = "rules"
os.environ.pop("OLLAMA_HOST", None)

from src.storage.memory_storage import InMemoryStorage
from src.models.message import MailMessage


class TestSearchBySender:
    """Tests for search_by_sender method."""

    def test_search_by_sender_exact_match(self, sample_emails):
        """Should find emails matching sender exactly."""
        results = sample_emails.search_by_sender("noreply@uber.com")
        
        assert len(results) >= 1
        assert all("uber" in r.from_.lower() for r in results)

    def test_search_by_sender_partial_match(self, sample_emails):
        """Should find emails with partial sender match."""
        results = sample_emails.search_by_sender("uber")
        
        assert len(results) >= 1
        assert all("uber" in r.from_.lower() for r in results)

    def test_search_by_sender_case_insensitive(self, sample_emails):
        """Should be case insensitive."""
        results_lower = sample_emails.search_by_sender("uber")
        results_upper = sample_emails.search_by_sender("UBER")
        results_mixed = sample_emails.search_by_sender("UbEr")
        
        assert len(results_lower) == len(results_upper) == len(results_mixed)

    def test_search_by_sender_no_match(self, sample_emails):
        """Should return empty list when no match."""
        results = sample_emails.search_by_sender("nonexistent@nowhere.xyz")
        
        assert results == []

    def test_search_by_sender_limit(self, sample_emails):
        """Should respect limit parameter."""
        results = sample_emails.search_by_sender("@", limit=3)
        
        assert len(results) <= 3

    def test_search_by_sender_sorted_by_date(self, sample_emails):
        """Should return results sorted by date (newest first)."""
        results = sample_emails.search_by_sender("@")  # Match all
        
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].internal_date >= results[i + 1].internal_date

    def test_search_by_sender_empty_database(self, empty_storage):
        """Should handle empty database."""
        results = empty_storage.search_by_sender("test")
        assert results == []


class TestSearchByAttachment:
    """Tests for search_by_attachment method."""

    def test_search_by_attachment_finds_attachments(self, sample_emails):
        """Should find emails with attachments."""
        results = sample_emails.search_by_attachment()
        
        assert len(results) > 0
        assert all(r.has_attachments for r in results)

    def test_search_by_attachment_limit(self, sample_emails):
        """Should respect limit parameter."""
        results = sample_emails.search_by_attachment(limit=2)
        
        assert len(results) <= 2

    def test_search_by_attachment_sorted_by_date(self, sample_emails):
        """Should return results sorted by date (newest first)."""
        results = sample_emails.search_by_attachment()
        
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].internal_date >= results[i + 1].internal_date

    def test_search_by_attachment_empty_database(self, empty_storage):
        """Should handle empty database."""
        results = empty_storage.search_by_attachment()
        assert results == []

    def test_search_by_attachment_no_attachments(self):
        """Should return empty when no emails have attachments."""
        storage = InMemoryStorage()
        storage.init_db()
        
        # Add email without attachment
        email = MailMessage(
            id="test1",
            from_="test@example.com",
            subject="No attachment",
            snippet="Plain email",
            has_attachments=False,
        )
        storage.save_message(email)
        
        results = storage.search_by_attachment()
        assert results == []


class TestSearchByKeywords:
    """Tests for search_by_keywords method."""

    def test_search_by_keywords_single_keyword(self, sample_emails):
        """Should find emails matching single keyword."""
        results = sample_emails.search_by_keywords(["uber"])
        
        assert len(results) > 0
        assert all(
            "uber" in (r.subject or "").lower() or 
            "uber" in (r.from_ or "").lower() or 
            "uber" in (r.snippet or "").lower()
            for r in results
        )

    def test_search_by_keywords_multiple_keywords(self, sample_emails):
        """Should find emails matching any keyword."""
        results = sample_emails.search_by_keywords(["uber", "amazon"])
        
        assert len(results) > 0
        # Each result should match at least one keyword
        for r in results:
            text = f"{r.subject or ''} {r.from_ or ''} {r.snippet or ''}".lower()
            assert "uber" in text or "amazon" in text

    def test_search_by_keywords_case_insensitive(self, sample_emails):
        """Should be case insensitive."""
        results_lower = sample_emails.search_by_keywords(["uber"])
        results_upper = sample_emails.search_by_keywords(["UBER"])
        
        assert len(results_lower) == len(results_upper)

    def test_search_by_keywords_no_match(self, sample_emails):
        """Should return empty list when no match."""
        results = sample_emails.search_by_keywords(["xyznonexistent123"])
        
        assert results == []

    def test_search_by_keywords_empty_list(self, sample_emails):
        """Should return empty for empty keyword list."""
        results = sample_emails.search_by_keywords([])
        
        assert results == []

    def test_search_by_keywords_limit(self, sample_emails):
        """Should respect limit parameter."""
        results = sample_emails.search_by_keywords(["@"], limit=3)
        
        assert len(results) <= 3

    def test_search_by_keywords_sorted_by_date(self, sample_emails):
        """Should return results sorted by date (newest first)."""
        results = sample_emails.search_by_keywords(["@"])
        
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].internal_date >= results[i + 1].internal_date

    def test_search_by_keywords_matches_subject(self, sample_emails):
        """Should match keywords in subject."""
        results = sample_emails.search_by_keywords(["shipped"])
        
        assert len(results) > 0
        assert any("shipped" in (r.subject or "").lower() for r in results)

    def test_search_by_keywords_matches_snippet(self, sample_emails):
        """Should match keywords in snippet."""
        results = sample_emails.search_by_keywords(["McDonald"])
        
        assert len(results) > 0


class TestCountByTopic:
    """Tests for count_by_topic method."""

    def test_count_by_topic_uber(self, sample_emails):
        """Should count uber-related emails."""
        count = sample_emails.count_by_topic("uber")
        
        assert count == 2  # 2 uber emails in sample_emails

    def test_count_by_topic_amazon(self, sample_emails):
        """Should count amazon-related emails."""
        count = sample_emails.count_by_topic("amazon")
        
        assert count == 2  # 2 amazon emails

    def test_count_by_topic_case_insensitive(self, sample_emails):
        """Should be case insensitive."""
        count_lower = sample_emails.count_by_topic("uber")
        count_upper = sample_emails.count_by_topic("UBER")
        
        assert count_lower == count_upper

    def test_count_by_topic_no_match(self, sample_emails):
        """Should return 0 when no match."""
        count = sample_emails.count_by_topic("xyznonexistent123")
        
        assert count == 0

    def test_count_by_topic_empty_database(self, empty_storage):
        """Should return 0 for empty database."""
        count = empty_storage.count_by_topic("test")
        
        assert count == 0


class TestGetDailyEmailStats:
    """Tests for get_daily_email_stats method."""

    def test_get_daily_email_stats_returns_data(self, sample_emails):
        """Should return daily statistics."""
        stats = sample_emails.get_daily_email_stats()
        
        assert len(stats) > 0
        assert all("date" in s and "count" in s for s in stats)

    def test_get_daily_email_stats_sorted_by_date(self, sample_emails):
        """Should return stats sorted by date (newest first)."""
        stats = sample_emails.get_daily_email_stats()
        
        if len(stats) > 1:
            for i in range(len(stats) - 1):
                assert stats[i]['date'] >= stats[i + 1]['date']

    def test_get_daily_email_stats_limit(self, sample_emails):
        """Should respect days limit."""
        stats = sample_emails.get_daily_email_stats(days=5)
        
        assert len(stats) <= 5

    def test_get_daily_email_stats_empty_database(self, empty_storage):
        """Should return empty for empty database."""
        stats = empty_storage.get_daily_email_stats()
        
        assert stats == []

    def test_get_daily_email_stats_groups_by_date(self):
        """Should group emails by date correctly."""
        storage = InMemoryStorage()
        storage.init_db()
        
        # Add 2 emails on same day
        base_ts = 1733050800000  # Dec 1, 2025
        
        storage.save_message(MailMessage(id="e1", subject="Email 1", internal_date=base_ts))
        storage.save_message(MailMessage(id="e2", subject="Email 2", internal_date=base_ts + 3600000))  # +1 hour
        
        stats = storage.get_daily_email_stats()
        
        # Should have 1 date entry with count 2
        assert len(stats) == 1
        assert stats[0]['count'] == 2


class TestGetTopSenders:
    """Tests for get_top_senders method."""

    def test_get_top_senders_returns_data(self, sample_emails):
        """Should return top senders."""
        senders = sample_emails.get_top_senders()
        
        assert len(senders) > 0
        assert all("from_addr" in s and "count" in s for s in senders)

    def test_get_top_senders_sorted_by_count(self, sample_emails):
        """Should return senders sorted by count (highest first)."""
        senders = sample_emails.get_top_senders()
        
        if len(senders) > 1:
            for i in range(len(senders) - 1):
                assert senders[i]['count'] >= senders[i + 1]['count']

    def test_get_top_senders_limit(self, sample_emails):
        """Should respect limit parameter."""
        senders = sample_emails.get_top_senders(limit=3)
        
        assert len(senders) <= 3

    def test_get_top_senders_empty_database(self, empty_storage):
        """Should return empty for empty database."""
        senders = empty_storage.get_top_senders()
        
        assert senders == []

    def test_get_top_senders_counts_correctly(self):
        """Should count sender occurrences correctly."""
        storage = InMemoryStorage()
        storage.init_db()
        
        # Add multiple emails from same sender
        for i in range(3):
            storage.save_message(MailMessage(
                id=f"e{i}",
                from_="frequent@example.com",
                subject=f"Email {i}",
            ))
        
        storage.save_message(MailMessage(
            id="e3",
            from_="once@example.com",
            subject="Single email",
        ))
        
        senders = storage.get_top_senders()
        
        # frequent@example.com should be first with count 3
        assert senders[0]['from_addr'] == "frequent@example.com"
        assert senders[0]['count'] == 3


class TestGetTotalMessageCount:
    """Tests for get_total_message_count method."""

    def test_get_total_message_count(self, sample_emails):
        """Should return correct total count."""
        count = sample_emails.get_total_message_count()
        
        assert count == 10  # 10 emails in sample_emails fixture

    def test_get_total_message_count_empty(self, empty_storage):
        """Should return 0 for empty database."""
        count = empty_storage.get_total_message_count()
        
        assert count == 0

    def test_get_total_message_count_after_adding(self, empty_storage):
        """Should update after adding messages."""
        assert empty_storage.get_total_message_count() == 0
        
        empty_storage.save_message(MailMessage(id="e1", subject="Test"))
        assert empty_storage.get_total_message_count() == 1
        
        empty_storage.save_message(MailMessage(id="e2", subject="Test 2"))
        assert empty_storage.get_total_message_count() == 2


class TestGetUnreadCount:
    """Tests for get_unread_count method."""

    def test_get_unread_count(self, sample_emails):
        """Should return correct unread count."""
        count = sample_emails.get_unread_count()
        
        # 3 unread emails in sample_emails: uber1, linkedin1, work1
        assert count == 3

    def test_get_unread_count_empty(self, empty_storage):
        """Should return 0 for empty database."""
        count = empty_storage.get_unread_count()
        
        assert count == 0

    def test_get_unread_count_no_unread(self):
        """Should return 0 when no unread emails."""
        storage = InMemoryStorage()
        storage.init_db()
        
        storage.save_message(MailMessage(
            id="e1",
            subject="Read email",
            labels=["INBOX"],  # No UNREAD label
        ))
        
        count = storage.get_unread_count()
        assert count == 0

    def test_get_unread_count_detects_unread_label(self):
        """Should detect UNREAD label correctly."""
        storage = InMemoryStorage()
        storage.init_db()
        
        storage.save_message(MailMessage(
            id="e1",
            subject="Unread email",
            labels=["INBOX", "UNREAD"],
        ))
        
        storage.save_message(MailMessage(
            id="e2",
            subject="Read email",
            labels=["INBOX"],
        ))
        
        count = storage.get_unread_count()
        assert count == 1

    def test_get_unread_count_handles_none_labels(self):
        """Should handle emails with no labels."""
        storage = InMemoryStorage()
        storage.init_db()
        
        storage.save_message(MailMessage(
            id="e1",
            subject="No labels",
            labels=None,
        ))
        
        count = storage.get_unread_count()
        assert count == 0


class TestStorageMethodsIntegration:
    """Integration tests for storage methods working together."""

    def test_combined_queries(self, sample_emails):
        """Test multiple queries on same data."""
        # Get counts
        total = sample_emails.get_total_message_count()
        unread = sample_emails.get_unread_count()
        
        assert unread <= total
        
        # Get by sender
        uber_emails = sample_emails.search_by_sender("uber")
        uber_count = sample_emails.count_by_topic("uber")
        
        # Count should match search results
        assert len(uber_emails) == uber_count

    def test_all_methods_handle_empty_storage(self, empty_storage):
        """All methods should handle empty storage gracefully."""
        assert empty_storage.search_by_sender("test") == []
        assert empty_storage.search_by_attachment() == []
        assert empty_storage.search_by_keywords(["test"]) == []
        assert empty_storage.count_by_topic("test") == 0
        assert empty_storage.get_daily_email_stats() == []
        assert empty_storage.get_top_senders() == []
        assert empty_storage.get_total_message_count() == 0
        assert empty_storage.get_unread_count() == 0
