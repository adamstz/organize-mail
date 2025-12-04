"""Shared unit-test fixtures for RAG and handler tests.

This previously lived in `tests/unit/conftest.py` but is now moved here
for a clearer filename. The existing `tests/unit/conftest.py` will import
from this module to keep pytest behavior unchanged.
"""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import List

# Set rules provider for deterministic tests BEFORE any imports
os.environ["LLM_PROVIDER"] = "rules"
# Clear any API keys that might cause auto-detection to pick another provider
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("ORGANIZE_MAIL_LLM_CMD", None)

from src.models.message import MailMessage
from src.storage.memory_storage import InMemoryStorage
from src.services.llm_processor import LLMProcessor
from src.services.context_builder import ContextBuilder
from src.services.query_classifier import QueryClassifier
from src.services.embedding_service import EmbeddingService


@pytest.fixture
def sample_emails() -> InMemoryStorage:
    """Pre-populated InMemoryStorage with diverse test emails."""
    storage = InMemoryStorage()
    storage.init_db()

    # Base timestamp: Dec 1, 2025, 10:00 AM UTC in milliseconds
    base_ts = 1733050800000
    day_ms = 86400000  # milliseconds in a day

    emails = [
        # Uber Eats emails
        MailMessage(
            id="uber1",
            thread_id="t1",
            from_="noreply@uber.com",
            to="user@example.com",
            subject="Your Uber Eats order is on the way",
            snippet="Your order from McDonald's is being prepared",
            labels=["INBOX", "UNREAD"],
            internal_date=base_ts,
            has_attachments=False,
        ),
        MailMessage(
            id="uber2",
            thread_id="t2",
            from_="receipts@uber.com",
            to="user@example.com",
            subject="Your Uber Eats receipt",
            snippet="Total: $25.99. Thank you for your order.",
            labels=["INBOX"],
            internal_date=base_ts - day_ms,
            has_attachments=True,
        ),
        # Amazon emails
        MailMessage(
            id="amazon1",
            thread_id="t3",
            from_="shipment-tracking@amazon.com",
            to="user@example.com",
            subject="Your Amazon order has shipped",
            snippet="Your package will arrive by Thursday",
            labels=["INBOX"],
            internal_date=base_ts - 2 * day_ms,
            has_attachments=False,
        ),
        MailMessage(
            id="amazon2",
            thread_id="t4",
            from_="no-reply@amazon.com",
            to="user@example.com",
            subject="Your Amazon.com order confirmation",
            snippet="Order #123-456-789 confirmed. Invoice attached.",
            labels=["INBOX"],
            internal_date=base_ts - 3 * day_ms,
            has_attachments=True,
        ),
        # LinkedIn emails
        MailMessage(
            id="linkedin1",
            thread_id="t5",
            from_="notifications@linkedin.com",
            to="user@example.com",
            subject="John Doe accepted your connection request",
            snippet="You and John Doe are now connected",
            labels=["INBOX", "UNREAD"],
            internal_date=base_ts - 4 * day_ms,
            has_attachments=False,
        ),
        # GitHub emails
        MailMessage(
            id="github1",
            thread_id="t6",
            from_="notifications@github.com",
            to="user@example.com",
            subject="[repo/project] Pull request #42: Fix bug",
            snippet="@contributor opened a new pull request",
            labels=["INBOX"],
            internal_date=base_ts - 5 * day_ms,
            has_attachments=False,
        ),
        # Work email with attachment
        MailMessage(
            id="work1",
            thread_id="t7",
            from_="boss@company.com",
            to="user@example.com",
            subject="Q4 Budget Review - Action Required",
            snippet="Please review the attached budget spreadsheet",
            labels=["INBOX", "UNREAD"],
            internal_date=base_ts - 6 * day_ms,
            has_attachments=True,
        ),
        # Personal email
        MailMessage(
            id="personal1",
            thread_id="t8",
            from_="friend@gmail.com",
            to="user@example.com",
            subject="Dinner plans for Saturday?",
            snippet="Hey! Are you free for dinner this weekend?",
            labels=["INBOX"],
            internal_date=base_ts - 7 * day_ms,
            has_attachments=False,
        ),
        # Newsletter
        MailMessage(
            id="newsletter1",
            thread_id="t9",
            from_="newsletter@techcrunch.com",
            to="user@example.com",
            subject="TechCrunch Daily: AI News Roundup",
            snippet="Today's top stories in artificial intelligence",
            labels=["INBOX"],
            internal_date=base_ts - 8 * day_ms,
            has_attachments=False,
        ),
        # Invoice email
        MailMessage(
            id="invoice1",
            thread_id="t10",
            from_="billing@spotify.com",
            to="user@example.com",
            subject="Your Spotify Premium invoice",
            snippet="Your monthly subscription has been renewed. Invoice attached.",
            labels=["INBOX"],
            internal_date=base_ts - 9 * day_ms,
            has_attachments=True,
        ),
    ]

    for email in emails:
        storage.save_message(email)

    storage.create_classification(
        message_id="uber1",
        labels=["food-delivery", "receipts"],
        priority="low",
        summary="Uber Eats order notification",
        model="rules"
    )
    storage.create_classification(
        message_id="uber2",
        labels=["food-delivery", "receipts", "finance"],
        priority="low",
        summary="Uber Eats receipt",
        model="rules"
    )
    storage.create_classification(
        message_id="amazon1",
        labels=["shopping", "shipping"],
        priority="medium",
        summary="Amazon shipment notification",
        model="rules"
    )
    storage.create_classification(
        message_id="work1",
        labels=["work", "finance", "action-required"],
        priority="high",
        summary="Budget review request from boss",
        model="rules"
    )
    storage.create_classification(
        message_id="linkedin1",
        labels=["social", "networking"],
        priority="low",
        summary="LinkedIn connection accepted",
        model="rules"
    )

    return storage


@pytest.fixture
def llm_processor() -> LLMProcessor:
    """LLM processor configured with rules provider for deterministic tests.

    Patches _is_ollama_running to avoid network timeout when Ollama is not available.
    """
    with patch.object(LLMProcessor, '_is_ollama_running', return_value=False):
        return LLMProcessor()


@pytest.fixture
def context_builder() -> ContextBuilder:
    """Context builder instance."""
    return ContextBuilder()


@pytest.fixture
def query_classifier(llm_processor) -> QueryClassifier:
    """Query classifier with rules-based LLM."""
    return QueryClassifier(llm_processor)


@pytest.fixture
def mock_embedding_service() -> Mock:
    """Mock EmbeddingService that returns deterministic embeddings.

    Returns a 384-dimensional vector (same as all-MiniLM-L6-v2).
    The mock tracks calls and can be configured for specific test scenarios.
    """
    mock_embedder = Mock(spec=EmbeddingService)

    default_embedding = [0.1] * 384
    mock_embedder.embed_text.return_value = default_embedding
    mock_embedder.embed_batch.return_value = [default_embedding]
    mock_embedder.model_name = "mock-model"
    mock_embedder.embedding_dim = 384

    return mock_embedder


@pytest.fixture
def handler_dependencies(sample_emails, llm_processor, context_builder, mock_embedding_service):
    """Common dependencies for all query handlers.

The file was created successfully.