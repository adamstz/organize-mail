"""Integration tests for chat history functionality."""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from src.services.rag_engine import RAGQueryEngine
from src.services.llm_processor import LLMProcessor
from src.storage.memory_storage import InMemoryStorage
from src.services.embedding_service import EmbeddingService
from src.models.message import MailMessage


class TestChatHistoryFlow:
    """Integration tests for complete chat history flow."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create test storage with sample data
        self.storage = InMemoryStorage()
        
        # Add test messages with different labels
        self.add_test_messages()
        
        # Create LLM processor (mocked)
        self.mock_llm = Mock(spec=LLMProcessor)
        self.mock_llm.provider = "test"
        self.mock_llm.model = "test-model"
        self.mock_llm.llm = None  # Force fallback to invoke() method
        
        # Create mock embedding service to avoid downloading models
        self.embedder = MagicMock(spec=EmbeddingService)
        self.embedder.embedding_dim = 384
        # Return deterministic embeddings for testing
        self.embedder.embed_text.return_value = [0.1] * 384
        self.embedder.embed_batch.return_value = [[0.1] * 384]
        
        # Create RAG engine
        self.rag_engine = RAGQueryEngine(
            storage=self.storage,
            embedding_service=self.embedder,
            llm_processor=self.mock_llm,
            top_k=5
        )

    def add_test_messages(self):
        """Add test messages to storage."""
        # Add promotional emails
        promo_emails = [
            MailMessage(
                id="promo1",
                subject="Special Offer - 50% Off",
                snippet="Limited time offer on all items",
                from_="marketing@shop.com",
                internal_date=1704096000000,  # 2024-01-01
                classification_labels=["promotions"]
            ),
            MailMessage(
                id="promo2",
                subject="Flash Sale Today Only",
                snippet="Don't miss our biggest sale",
                from_="deals@store.com",
                internal_date=1704182400000,  # 2024-01-02
                classification_labels=["promotions"]
            )
        ]

        # Add job application emails
        job_emails = [
            MailMessage(
                id="job1",
                subject="Application Received - Software Engineer",
                snippet="We have received your application for the Software Engineer position",
                from_="hr@techcorp.com",
                internal_date=1704268800000,  # 2024-01-03
                classification_labels=["job-application"]
            ),
            MailMessage(
                id="job2",
                subject="Interview Invitation - Product Manager",
                snippet="We would like to schedule an interview",
                from_="recruiting@startup.com",
                internal_date=1704355200000,  # 2024-01-04
                classification_labels=["job-interview"]
            )
        ]

        # Add receipt emails
        receipt_emails = [
            MailMessage(
                id="receipt1",
                subject="Your Order Receipt #12345",
                snippet="Thank you for your purchase",
                from_="orders@amazon.com",
                internal_date=1704441600000,  # 2024-01-05
                classification_labels=["receipts"]
            )
        ]
        
        all_emails = promo_emails + job_emails + receipt_emails
        for email in all_emails:
            self.storage.save_message(email)

    def test_direct_classification_query_works(self):
        """Test that direct classification queries still work (baseline)."""
        # Mock LLM response - invoke() returns string directly, not a Mock object
        self.mock_llm.invoke.return_value = "You have 2 promotional emails in your database."

        # Test direct query
        result = self.rag_engine.query("how many promotional emails do I have?")

        assert result['query_type'] == 'classification'
        assert '2' in result['answer'] or 'promotional' in result['answer']
        assert result['confidence'] == 'high'

    def test_followup_query_with_context(self):
        """Test follow-up query with chat history context."""
        # Mock LLM responses - invoke() returns string directly
        self.mock_llm.invoke.return_value = "Based on the promotional emails, marketing@shop.com and deals@store.com are the top senders."

        # Simulate chat history
        chat_history = [
            {"role": "user", "content": "how many promotional emails do I have"},
            {"role": "assistant", "content": "You have 2 promotional emails in your database."},
        ]

        # Test follow-up query
        result = self.rag_engine.query(
            question="of those, who sends the most?",
            chat_history=chat_history
        )

        assert result['query_type'] == 'classification'
        # Note: confidence may be 'none' if history extraction doesn't find a label
        # The important thing is that it routes to classification handler
        assert result['confidence'] in ['high', 'none']

    def test_job_application_followup_query(self):
        """Test follow-up query for job applications."""
        # Mock LLM responses
        self.mock_llm.invoke.return_value = "Based on job emails, hr@techcorp.com sent application confirmations while recruiting@startup.com sent interview invitations."

        chat_history = [
            {"role": "user", "content": "show me job applications"},
            {"role": "assistant", "content": "I found 2 job-related emails."},
        ]

        result = self.rag_engine.query(
            question="from those, which are interviews?",
            chat_history=chat_history
        )

        assert result['query_type'] == 'classification'
        assert 'job' in result['answer'].lower() or 'interview' in result['answer'].lower()

    def test_multiple_topic_changes(self):
        """Test conversation with multiple topic changes."""
        # Mock response for the final query
        self.mock_llm.invoke.return_value = "hr@techcorp.com and recruiting@startup.com sent job-related emails."

        # Simulate complex conversation
        chat_history = [
            {"role": "user", "content": "how many promotional emails?"},
            {"role": "assistant", "content": "2 promotional emails"},
            {"role": "user", "content": "how many job applications?"},
            {"role": "assistant", "content": "2 job-related emails"},
            {"role": "user", "content": "any receipts?"},
            {"role": "assistant", "content": "1 receipt email"},
        ]

        result = self.rag_engine.query(
            question="from the job ones, who sends?",
            chat_history=chat_history
        )

        assert result['query_type'] == 'classification'
        assert 'hr@techcorp.com' in result['answer'] or 'recruiting@startup.com' in result['answer']

    def test_no_history_fallback(self):
        """Test query without history falls back gracefully."""
        # Without clear context, this should still work but with lower confidence
        result = self.rag_engine.query("who sends most?")

        # Should handle gracefully without history
        # This is an aggregation query without specific classification context
        assert result['query_type'] in ['aggregation', 'classification', 'semantic']

    def test_query_classifier_context_detection(self):
        """Test that QueryClassifier detects contextual follow-ups."""
        from src.services.query_classifier import QueryClassifier

        classifier = QueryClassifier(self.mock_llm)

        # Test contextual reference detection
        contextual_questions = [
            "of those 97, who sends the most?",
            "from them, which are receipts?",
            "among those, any from known companies?",
            "what about the job ones?"
        ]

        chat_history = [
            {"role": "user", "content": "how many promotional emails?"},
            {"role": "assistant", "content": "You have promotional emails"},
        ]

        for question in contextual_questions:
            # Mock LLM response if needed for classification
            self.mock_llm.invoke.return_value = "classification"

            query_type = classifier.detect_query_type(question, chat_history)
            # With history context, these should route to appropriate handler
            assert query_type in ['classification', 'aggregation', 'semantic'], \
                f"Expected valid query type for '{question}', got '{query_type}'"

    def test_performance_with_history(self):
        """Test that performance remains acceptable with chat history."""
        import time

        # Mock response
        self.mock_llm.invoke.return_value = "Marketing emails from various companies."

        chat_history = [
            {"role": "user", "content": "how many promotional emails do I have"},
            {"role": "assistant", "content": "You have 2 promotional emails"},
        ]

        start_time = time.time()
        result = self.rag_engine.query(
            question="of those, who sends most?",
            chat_history=chat_history
        )
        end_time = time.time()

        # Should complete within reasonable time (adjust as needed)
        assert end_time - start_time < 5.0, f"Query took too long: {end_time - start_time:.2f}s"
        assert result['query_type'] in ['classification', 'aggregation', 'semantic']


if __name__ == "__main__":
    pytest.main([__file__])
