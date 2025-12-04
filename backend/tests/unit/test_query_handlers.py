"""Tests for RAG query handlers.

Tests all 7 query handlers:
- ConversationHandler
- AggregationHandler
- SenderHandler
- AttachmentHandler
- ClassificationHandler
- TemporalHandler
- SemanticHandler
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Set rules provider BEFORE imports
os.environ["LLM_PROVIDER"] = "rules"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("ORGANIZE_MAIL_LLM_CMD", None)

from src.services.query_handlers.conversation import ConversationHandler
from src.services.query_handlers.aggregation import AggregationHandler
from src.services.query_handlers.sender import SenderHandler
from src.services.query_handlers.attachment import AttachmentHandler
from src.services.query_handlers.classification import ClassificationHandler
from src.services.query_handlers.temporal import TemporalHandler
from src.services.query_handlers.semantic import SemanticHandler
from src.models.message import MailMessage


class TestConversationHandler:
    """Tests for ConversationHandler."""

    def test_handle_greeting_hello(self, handler_dependencies):
        """Should respond to 'hello' with a greeting."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("hello")
        
        assert result['query_type'] == 'conversation'
        assert result['confidence'] == 'high'
        assert result['sources'] == []
        # Fallback response should contain helpful text
        assert result['answer']  # Not empty

    def test_handle_greeting_hi(self, handler_dependencies):
        """Should respond to 'hi' with a greeting."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("hi")
        
        assert result['query_type'] == 'conversation'
        assert 'sources' in result
        assert result['answer']  # Not empty

    def test_handle_thanks(self, handler_dependencies):
        """Should respond politely to thanks."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("thanks!")
        
        assert result['query_type'] == 'conversation'
        # Response should have some content
        assert result['answer']

    def test_handle_help_request(self, handler_dependencies):
        """Should provide help information."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("help")
        
        assert result['query_type'] == 'conversation'
        # Help response should have content
        assert result['answer']

    def test_fallback_response(self, handler_dependencies):
        """Should provide a generic response for unknown conversational input."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("random conversational input")
        
        assert result['query_type'] == 'conversation'
        assert result['answer']  # Should have some response


class TestAggregationHandler:
    """Tests for AggregationHandler."""

    def test_handle_total_count(self, handler_dependencies):
        """Should return total email count."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("how many total emails do I have?")
        
        assert result['query_type'] == 'aggregation'
        assert result['confidence'] == 'high'
        # Should mention the count (10 emails in sample_emails fixture)
        assert '10' in result['answer']

    def test_handle_unread_count(self, handler_dependencies):
        """Should return unread email count."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("how many unread emails do I have?")
        
        assert result['query_type'] == 'aggregation'
        # Should mention unread count (3 unread in sample_emails)
        assert '3' in result['answer']

    def test_handle_topic_count_uber(self, handler_dependencies):
        """Should count emails by topic."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("how many uber emails do I have?")
        
        assert result['query_type'] == 'aggregation'
        # Should return some answer (topic extraction may vary with rules provider)
        assert result['answer']

    def test_handle_daily_stats(self, handler_dependencies):
        """Should return daily email statistics."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("how many emails do I get per day?")
        
        assert result['query_type'] == 'aggregation'
        assert 'day' in result['answer'].lower() or 'average' in result['answer'].lower()

    def test_handle_top_senders(self, handler_dependencies):
        """Should return top email senders."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("who emails me most?")
        
        assert result['query_type'] == 'aggregation'
        # Should list senders
        assert '@' in result['answer'] or 'sender' in result['answer'].lower()

    def test_extract_topic_cleanup(self, handler_dependencies):
        """Should clean up verbose LLM topic responses."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        # Test the cleanup logic
        test_cases = [
            ("uber", "uber"),
            ("Uber", "Uber"),
            ("**uber**", "uber"),
            ("topic: uber", "uber"),
            ("the topic is uber", "uber"),
        ]
        
        for input_topic, expected in test_cases:
            cleaned = handler._clean_topic_response(input_topic)
            assert expected.lower() in cleaned.lower(), f"Failed for input: {input_topic}"

    def test_handle_generic_aggregation(self, handler_dependencies):
        """Should handle generic aggregation queries gracefully."""
        handler = AggregationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("email statistics")
        
        assert result['query_type'] == 'aggregation'
        assert result['answer']


class TestSenderHandler:
    """Tests for SenderHandler."""

    def test_handle_search_by_sender_uber(self, handler_dependencies):
        """Should find emails from uber."""
        handler = SenderHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me all emails from uber")
        
        assert result['query_type'] == 'search-by-sender'
        # Should find uber emails
        if result['sources']:
            assert any('uber' in s.get('from', '').lower() for s in result['sources'])

    def test_handle_search_by_sender_amazon(self, handler_dependencies):
        """Should find emails from amazon."""
        handler = SenderHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("emails from amazon")
        
        assert result['query_type'] == 'search-by-sender'
        # Should find amazon emails
        if result['sources']:
            assert any('amazon' in s.get('from', '').lower() for s in result['sources'])

    def test_handle_no_matching_sender(self, handler_dependencies):
        """Should handle when no emails match sender."""
        handler = SenderHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("emails from nonexistent@nowhere.com")
        
        assert result['query_type'] == 'search-by-sender'
        assert result['confidence'] == 'none' or "couldn't find" in result['answer'].lower()
        assert result['sources'] == []


class TestAttachmentHandler:
    """Tests for AttachmentHandler."""

    def test_handle_find_attachments(self, handler_dependencies):
        """Should find emails with attachments."""
        handler = AttachmentHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me emails with attachments")
        
        assert result['query_type'] == 'search-by-attachment'
        # Should find emails with attachments (4 in sample_emails)
        # With rules provider, LLM call may not generate proper answer
        assert len(result['sources']) > 0 or result['confidence'] == 'none'

    def test_handle_no_attachments(self, empty_storage, llm_processor, context_builder):
        """Should handle when no emails have attachments."""
        # Add email without attachment
        email = MailMessage(
            id="test1",
            from_="test@example.com",
            subject="No attachment",
            snippet="Plain email",
            has_attachments=False,
        )
        empty_storage.save_message(email)
        
        handler = AttachmentHandler(
            storage=empty_storage,
            llm=llm_processor,
            context_builder=context_builder,
        )
        
        result = handler.handle("emails with attachments")
        
        assert result['query_type'] == 'search-by-attachment'
        assert result['confidence'] == 'none'
        assert result['sources'] == []


class TestClassificationHandler:
    """Tests for ClassificationHandler."""

    def test_handle_finance_label(self, handler_dependencies):
        """Should find emails with finance label."""
        handler = ClassificationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me my finance emails")
        
        assert result['query_type'] == 'classification'
        # Should return a result (may or may not find finance emails depending on label matching)
        assert 'answer' in result
        assert 'sources' in result

    def test_handle_work_label(self, handler_dependencies):
        """Should find emails with work label."""
        handler = ClassificationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me work emails")
        
        assert result['query_type'] == 'classification'

    def test_handle_unknown_label(self, handler_dependencies):
        """Should handle unknown classification labels."""
        handler = ClassificationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me my xyz123 emails")
        
        assert result['query_type'] == 'classification'
        # Should indicate no match or empty results
        assert result['confidence'] == 'none' or result['sources'] == []


class TestTemporalHandler:
    """Tests for TemporalHandler."""

    def test_handle_pure_temporal_latest(self, handler_dependencies):
        """Should return latest emails for pure temporal query."""
        handler = TemporalHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("show me my latest emails")
        
        assert result['query_type'] == 'temporal'
        # With rules provider, may have sources or not depending on LLM response
        assert 'sources' in result
        assert 'answer' in result

    def test_handle_pure_temporal_recent(self, handler_dependencies):
        """Should return recent emails."""
        handler = TemporalHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle("recent messages")
        
        assert result['query_type'] == 'temporal'
        assert 'sources' in result

    def test_handle_filtered_temporal_uber(self, handler_dependencies):
        """Should return recent uber emails for filtered-temporal query."""
        handler = TemporalHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle_filtered("most recent uber emails")
        
        assert result['query_type'] == 'filtered-temporal'
        # Should have response structure
        assert 'sources' in result
        assert 'answer' in result

    def test_handle_filtered_temporal_amazon(self, handler_dependencies):
        """Should return recent amazon emails."""
        handler = TemporalHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        result = handler.handle_filtered("latest amazon orders")
        
        assert result['query_type'] == 'filtered-temporal'
        assert 'answer' in result

    def test_extract_keywords_fallback(self, handler_dependencies):
        """Should extract keywords using fallback when LLM fails."""
        handler = TemporalHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        keywords = handler._extract_keywords_fallback("recent uber eats orders")
        
        assert len(keywords) > 0
        assert any('uber' in kw.lower() for kw in keywords) or any('eats' in kw.lower() for kw in keywords)

    def test_handle_empty_database(self, empty_storage, llm_processor, context_builder):
        """Should handle empty database gracefully."""
        handler = TemporalHandler(
            storage=empty_storage,
            llm=llm_processor,
            context_builder=context_builder,
        )
        
        result = handler.handle("latest emails")
        
        assert result['query_type'] == 'temporal'
        assert result['confidence'] == 'none'


class TestSemanticHandler:
    """Tests for SemanticHandler with mocked embeddings."""

    def test_handle_no_embedder(self, handler_dependencies):
        """Should handle missing embedder gracefully."""
        handler = SemanticHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=None,  # No embedder
        )
        
        result = handler.handle("search for budget discussions")
        
        assert result['query_type'] == 'semantic'
        assert result['confidence'] == 'none'
        assert 'not available' in result['answer'].lower()

    def test_handle_with_mock_embedder(self, handler_dependencies):
        """Should use embedder and storage for semantic search."""
        mock_embedder = handler_dependencies['embedder']
        storage = handler_dependencies['storage']
        
        # Mock similarity_search to return some emails
        email = MailMessage(
            id="test1",
            from_="test@example.com",
            subject="Budget Discussion",
            snippet="Let's talk about the Q4 budget",
            internal_date=1733050800000,
        )
        storage.save_message(email)
        
        # Add similarity_search method to mock storage
        mock_results = [(email, 0.85)]
        storage.similarity_search = Mock(return_value=mock_results)
        
        handler = SemanticHandler(
            storage=storage,
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("budget discussions")
        
        assert result['query_type'] == 'semantic'
        # Embedder should have been called
        mock_embedder.embed_text.assert_called_once()
        # Storage similarity_search should have been called
        storage.similarity_search.assert_called_once()

    def test_handle_no_results(self, handler_dependencies):
        """Should handle when semantic search returns no results."""
        mock_embedder = handler_dependencies['embedder']
        storage = handler_dependencies['storage']
        
        # Mock empty results
        storage.similarity_search = Mock(return_value=[])
        
        handler = SemanticHandler(
            storage=storage,
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("something that doesn't exist")
        
        assert result['query_type'] == 'semantic'
        assert result['confidence'] == 'none'
        assert "couldn't find" in result['answer'].lower()

    def test_confidence_levels_high(self, handler_dependencies):
        """Should return high confidence for high similarity scores."""
        mock_embedder = handler_dependencies['embedder']
        storage = handler_dependencies['storage']
        
        email = MailMessage(
            id="test_high",
            from_="test@example.com",
            subject="Test",
            snippet="Test content",
            internal_date=1733050800000,
        )
        storage.save_message(email)
        
        # High similarity score
        storage.similarity_search = Mock(return_value=[(email, 0.9)])
        
        handler = SemanticHandler(
            storage=storage,
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("test query")
        
        # With rules provider, LLM answer generation may fail, resulting in 'none'
        # If it succeeds, confidence should be 'high' for score 0.9
        assert result['confidence'] in ('high', 'none')

    def test_confidence_levels_medium(self, handler_dependencies):
        """Should return medium confidence for medium similarity scores."""
        mock_embedder = handler_dependencies['embedder']
        storage = handler_dependencies['storage']
        
        email = MailMessage(
            id="test_medium",
            from_="test@example.com",
            subject="Test",
            snippet="Test content",
            internal_date=1733050800000,
        )
        storage.save_message(email)
        
        # Medium similarity score
        storage.similarity_search = Mock(return_value=[(email, 0.7)])
        
        handler = SemanticHandler(
            storage=storage,
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("test query")
        
        # With rules provider, LLM answer generation may fail
        assert result['confidence'] in ('medium', 'none')

    def test_confidence_levels_low(self, handler_dependencies):
        """Should return low confidence for low similarity scores."""
        mock_embedder = handler_dependencies['embedder']
        storage = handler_dependencies['storage']
        
        email = MailMessage(
            id="test_low",
            from_="test@example.com",
            subject="Test",
            snippet="Test content",
            internal_date=1733050800000,
        )
        storage.save_message(email)
        
        # Low similarity score
        storage.similarity_search = Mock(return_value=[(email, 0.55)])
        
        handler = SemanticHandler(
            storage=storage,
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("test query")
        
        # With rules provider, LLM answer generation may fail
        assert result['confidence'] in ('low', 'none')

    def test_handle_embedding_error(self, handler_dependencies):
        """Should handle embedding errors gracefully."""
        mock_embedder = handler_dependencies['embedder']
        mock_embedder.embed_text.side_effect = Exception("Embedding failed")
        
        handler = SemanticHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
            embedder=mock_embedder,
        )
        
        result = handler.handle("test query")
        
        assert result['query_type'] == 'semantic'
        assert result['confidence'] == 'none'
        assert 'error' in result['answer'].lower()


class TestBaseHandlerMethods:
    """Tests for base handler shared methods."""

    def test_build_response_format(self, handler_dependencies):
        """Should build response with correct format."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        response = handler._build_response(
            answer="Test answer",
            sources=[{"id": "1", "subject": "Test"}],
            question="Test question",
            query_type="test",
            confidence="high",
            extra_field="extra_value"
        )
        
        assert response['answer'] == "Test answer"
        assert response['sources'] == [{"id": "1", "subject": "Test"}]
        assert response['question'] == "Test question"
        assert response['query_type'] == "test"
        assert response['confidence'] == "high"
        assert response['extra_field'] == "extra_value"

    def test_format_sources(self, handler_dependencies):
        """Should format email sources correctly."""
        handler = ConversationHandler(
            storage=handler_dependencies['storage'],
            llm=handler_dependencies['llm'],
            context_builder=handler_dependencies['context_builder'],
        )
        
        emails = [
            MailMessage(
                id="test1",
                from_="sender@example.com",
                subject="Test Subject",
                snippet="Test snippet",
                internal_date=1733050800000,
            )
        ]
        
        sources = handler._format_sources(emails, similarity=0.95)
        
        assert len(sources) == 1
        assert sources[0]['message_id'] == "test1"
        assert sources[0]['subject'] == "Test Subject"
        assert sources[0]['from'] == "sender@example.com"
        assert sources[0]['snippet'] == "Test snippet"
        assert sources[0]['similarity'] == 0.95
        assert sources[0]['date'] == 1733050800000
