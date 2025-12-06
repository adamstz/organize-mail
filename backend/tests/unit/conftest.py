"""
Unit test fixtures for RAG components.

This conftest.py provides shared fixtures for unit tests, including:
- Sample email data (sample_emails fixture)
- LLM processor with rules provider (llm_processor fixture)
- Query classifier (query_classifier fixture)
- Context builder (context_builder fixture)
- Storage instances (empty_storage, sample_emails fixtures)
- Handler dependencies bundle (handler_dependencies fixture)

Note: pytest requires the filename 'conftest.py' for automatic fixture discovery.
"""
import os
from unittest.mock import patch, MagicMock

import pytest

from src.storage.memory_storage import InMemoryStorage
from src.services.llm_processor import LLMProcessor
from src.services.query_classifier import QueryClassifier
from src.services.context_builder import ContextBuilder
from src.models.message import MailMessage


def make_email(
    id: str,
    subject: str,
    sender: str,
    snippet: str,
    date_ts: int,
    labels: list[str] | None = None,
    has_attachments: bool = False,
) -> MailMessage:
    """Helper function to create email MailMessage objects for testing."""
    return MailMessage(
        id=id,
        thread_id=f"thread_{id}",
        subject=subject,
        from_=sender,
        snippet=snippet,
        internal_date=date_ts * 1000,  # internal_date is in milliseconds
        labels=labels or [],
        has_attachments=has_attachments,
    )


@pytest.fixture
def sample_emails():
    """
    Create an InMemoryStorage with sample email data for testing.
    
    Returns a storage instance populated with 10 test emails from various
    senders (Uber, Amazon, GitHub, LinkedIn, etc.) with different attributes
    for testing search, filtering, and aggregation functionality.
    
    Includes:
    - 2 Uber emails (one ride, one Uber Eats with McDonald's)
    - 2 Amazon emails (both with attachments)
    - 1 GitHub notification
    - 1 LinkedIn connection request (unread)
    - 1 Work email (unread)
    - 3 emails with UNREAD labels
    """
    storage = InMemoryStorage()
    storage.init_db()
    
    emails = [
        make_email(
            "1",
            "Your Uber receipt",
            "noreply@uber.com",
            "Thanks for riding with Uber. Your trip cost $25.",
            1699000000,
            ["receipts"],
            False,
        ),
        make_email(
            "2",
            "Amazon order shipped",
            "orders@amazon.com",
            "Your Amazon order has shipped. Track your package.",
            1699100000,
            ["shopping"],
            True,
        ),
        make_email(
            "3",
            "GitHub notification",
            "notifications@github.com",
            "New pull request in your repository.",
            1699200000,
            ["work"],
            False,
        ),
        make_email(
            "4",
            "Uber Eats delivery",
            "noreply@uber.com",
            "Your McDonald's order is on the way! Delivery in 30 minutes.",
            1699300000,
            ["food", "UNREAD"],
            False,
        ),
        make_email(
            "5",
            "LinkedIn connection",
            "linkedin@linkedin.com",
            "You have a new connection request.",
            1699400000,
            ["social", "UNREAD"],
            True,
        ),
        make_email(
            "6",
            "Amazon Prime Day deals",
            "deals@amazon.com",
            "Don't miss these exclusive Prime Day deals!",
            1699500000,
            ["promotions"],
            True,
        ),
        make_email(
            "7",
            "Work project update",
            "manager@company.com",
            "Please review the quarterly report by Friday.",
            1699600000,
            ["work", "UNREAD"],
            False,
        ),
        make_email(
            "8",
            "Newsletter weekly digest",
            "newsletter@example.com",
            "This week's top stories and updates.",
            1699700000,
            ["newsletter"],
            False,
        ),
        make_email(
            "9",
            "Bank statement",
            "noreply@bank.com",
            "Your monthly statement is ready to view.",
            1699800000,
            ["finance"],
            True,
        ),
        make_email(
            "10",
            "Meeting reminder",
            "calendar@company.com",
            "Reminder: Team meeting tomorrow at 10 AM.",
            1699900000,
            ["work"],
            False,
        ),
    ]
    
    for email in emails:
        storage.save_message(email)
    
    return storage


@pytest.fixture
def empty_storage():
    """Create an empty InMemoryStorage instance for testing edge cases."""
    storage = InMemoryStorage()
    storage.init_db()
    return storage


@pytest.fixture
def llm_processor():
    """
    Create an LLMProcessor configured with the 'rules' provider.
    
    The rules provider uses keyword-based classification without making
    actual LLM API calls, making tests deterministic and fast.
    """
    # Ensure LLM_PROVIDER is set to rules
    os.environ["LLM_PROVIDER"] = "rules"
    with patch.object(LLMProcessor, '_is_ollama_running', return_value=False):
        return LLMProcessor()


@pytest.fixture
def query_classifier(llm_processor):
    """Create a QueryClassifier instance using the rules-based LLM processor."""
    return QueryClassifier(llm_processor)


@pytest.fixture
def context_builder():
    """Create a ContextBuilder instance for testing context formatting."""
    return ContextBuilder()


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service that returns empty results."""
    mock = MagicMock()
    mock.search_similar.return_value = []
    return mock


@pytest.fixture
def handler_dependencies(sample_emails, llm_processor, context_builder, mock_embedding_service):
    """
    Bundle all common handler dependencies into a single fixture.
    
    Returns a dictionary with:
    - storage: InMemoryStorage with sample emails
    - llm: LLMProcessor with rules provider
    - context_builder: ContextBuilder instance
    - embedder: Mock embedding service
    """
    return {
        "storage": sample_emails,
        "llm": llm_processor,
        "context_builder": context_builder,
        "embedder": mock_embedding_service,
    }
