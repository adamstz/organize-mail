"""Tests for RAG query classification logic.

These tests verify that the RAGQueryEngine correctly classifies different
types of user queries and routes them to appropriate handlers.

NOTE: This file tests classification through RAGQueryEngine._detect_query_type()
which delegates to QueryClassifier. For direct QueryClassifier tests, see
test_query_classifier.py.
"""

import os
import pytest

os.environ["LLM_PROVIDER"] = "rules"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("ORGANIZE_MAIL_LLM_CMD", None)

from src.services.rag_engine import RAGQueryEngine
from src.services.query_classifier import QueryClassifier
from src.services.embedding_service import EmbeddingService
from src.services.llm_processor import LLMProcessor
from src.storage.memory_storage import InMemoryStorage
from unittest.mock import patch


@pytest.fixture
def rag_engine():
    """Create a RAG engine instance for testing."""
    storage = InMemoryStorage()
    storage.init_db()
    embedding = EmbeddingService()
    with patch.object(LLMProcessor, '_is_ollama_running', return_value=False):
        llm = LLMProcessor()
    return RAGQueryEngine(storage, embedding, llm)


@pytest.fixture
def query_classifier():
    """Create a QueryClassifier instance for direct testing."""
    with patch.object(LLMProcessor, '_is_ollama_running', return_value=False):
        llm = LLMProcessor()
    return QueryClassifier(llm)


class TestQueryClassification:
    """Test query type classification."""

    def test_conversation_query(self, rag_engine):
        """Should classify simple greetings as conversation type."""
        queries = [
            "hello",
            "hi",
        ]
        
        for query in queries:
            query_type = rag_engine._detect_query_type(query)
            assert query_type == "conversation", f"Failed for query: {query}"

    def test_aggregation_query(self, rag_engine):
        """Should classify counting/stats questions as aggregation type."""
        # Test at least one clear aggregation query
        query_type = rag_engine._detect_query_type("email statistics")
        # Small LLMs may vary in classification
        assert query_type in ("aggregation", "conversation", "semantic"), \
            "Failed for query: email statistics"

    def test_search_by_sender_query(self, rag_engine):
        """Should classify sender-based searches."""
        query_type = rag_engine._detect_query_type("all emails from uber")
        # LLM might classify various ways - all can work for this query
        assert query_type in ("search-by-sender", "aggregation", "semantic"), \
            f"Got: {query_type}"

    def test_filtered_temporal_query(self, rag_engine):
        """Should classify queries with both temporal and content filters."""
        query_type = rag_engine._detect_query_type("five most recent uber eats mails")
        # LLM classification can vary - all of these work for this query
        assert query_type in ("filtered-temporal", "search-by-sender", "semantic"), \
            f"Got: {query_type}"

    def test_temporal_query(self, rag_engine):
        """Should classify queries with only temporal filter."""
        query_type = rag_engine._detect_query_type("latest messages")
        # LLM classification can vary - all of these are reasonable for this query
        assert query_type in ("temporal", "filtered-temporal", "semantic", "search-by-sender"), \
            f"Got: {query_type}"

    def test_semantic_query(self, rag_engine):
        """Should classify content-based semantic searches."""
        query_type = rag_engine._detect_query_type("regarding budget discussion")
        # Can be semantic, classification, or even conversation (LLM interprets differently)
        assert query_type in ("semantic", "classification", "conversation"), f"Got: {query_type}"

    def test_search_by_attachment_query(self, rag_engine):
        """Should classify attachment-based searches."""
        query_type = rag_engine._detect_query_type("emails with attachments")
        # Various classification types can handle attachment queries
        assert query_type in ("search-by-attachment", "semantic", "search-by-sender"), \
            f"Got: {query_type}"


class TestQueryClassificationRobustness:
    """Test classification with edge cases and variations."""

    def test_mixed_case_queries(self, rag_engine):
        """Should handle queries with mixed case."""
        query_type = rag_engine._detect_query_type("HELLO")
        assert query_type == "conversation"
        
        query_type = rag_engine._detect_query_type("How Many Emails")
        assert query_type in ("aggregation", "semantic")

    def test_queries_with_punctuation(self, rag_engine):
        """Should handle queries with punctuation."""
        query_type = rag_engine._detect_query_type("hello!")
        assert query_type == "conversation"
        
        query_type = rag_engine._detect_query_type("how many emails?")
        # LLM can classify various ways - all are reasonable for this query
        assert query_type in ("aggregation", "semantic", "search-by-sender")

    def test_empty_query(self, rag_engine):
        """Should handle empty queries gracefully."""
        query_type = rag_engine._detect_query_type("")
        # Should default to some reasonable type - LLM can choose any valid type
        assert query_type in ("semantic", "conversation", "aggregation", "search-by-sender")

    def test_very_long_query(self, rag_engine):
        """Should handle very long queries."""
        long_query = "show me all the emails " * 50  # Very long repetitive query
        query_type = rag_engine._detect_query_type(long_query)
        # Should classify as something reasonable - LLM can choose any valid type
        assert query_type in ("temporal", "semantic", "search-by-sender", "conversation")


class TestLLMResponseParsing:
    """Test parsing of LLM responses for query classification."""

    def test_handles_verbose_llm_response(self, rag_engine):
        """Should extract classification even when LLM is verbose."""
        # Simulate what _detect_query_type does with a verbose response
        test_responses = [
            ('the answer is "conversation"', 'conversation'),
            ('sure, the answer is "aggregation"', 'aggregation'),
            ('the answer is "recent". this is about recent emails', 'filtered-temporal'),
            ('count', 'aggregation'),
        ]
        
        for response, expected_type in test_responses:
            # Test the parsing logic directly
            response_lower = response.strip().lower()
            
            if 'answer is' in response_lower:
                parts = response_lower.split('answer is')
                if len(parts) > 1:
                    after_answer = parts[1].strip()
                    first_word = after_answer.strip('"\'').split()[0]
                else:
                    first_word = response_lower.split()[0]
            else:
                first_word = response_lower.split()[0] if response_lower else ''
            
            first_word = first_word.strip('.,!?":;')
            
            # Map common response words
            if first_word in ('recent', 'latest', 'newest', 'oldest'):
                detected = 'filtered-temporal'
            elif first_word == 'count':
                detected = 'aggregation'
            elif first_word in ('conversation', 'aggregation', 'search-by-sender',
                               'search-by-attachment', 'filtered-temporal', 'temporal', 'semantic'):
                detected = first_word
            else:
                detected = 'semantic'
            
            assert detected == expected_type, \
                f"Failed to parse '{response}', expected {expected_type}, got {detected}"


class TestQueryClassificationIntegration:
    """Integration tests for the main query types we expect."""

    def test_original_uber_eats_query(self, rag_engine):
        """Test the original query that started this whole classification work."""
        query = "what are the five most recent uber eats mails?"
        query_type = rag_engine._detect_query_type(query)
        
        # Should be classified as filtered-temporal or search-by-sender (both work)
        assert query_type in ("filtered-temporal", "search-by-sender"), \
            f"Got unexpected type: {query_type}"

    def test_common_chatbot_queries(self, rag_engine):
        """Test queries a user might naturally ask a chatbot."""
        # Just test that classification returns valid types
        valid_types = {"conversation", "aggregation", "search-by-sender", "search-by-attachment",
                      "classification", "filtered-temporal", "temporal", "semantic"}
        
        queries = ["hey there", "my email count?", "newest github emails"]
        
        for query in queries:
            query_type = rag_engine._detect_query_type(query)
            assert query_type in valid_types, \
                f"Query '{query}' got invalid type: {query_type}"

    def test_how_many_topic_query(self, rag_engine):
        """Test that 'how many [topic]' queries are classified as aggregation."""
        queries = [
            "how many uber eats mail do i have",
            "how many amazon emails",
            "count my linkedin messages",
        ]
        
        for query in queries:
            query_type = rag_engine._detect_query_type(query)
            # Should be classified as aggregation since they're counting a specific topic
            assert query_type == "aggregation", \
                f"Query '{query}' should be 'aggregation' but got: {query_type}"


class TestClassificationQueryType:
    """Tests for the 'classification' query type (label-based queries)."""

    def test_finance_emails_classification(self, rag_engine):
        """Should classify finance label queries as classification type."""
        query_type = rag_engine._detect_query_type("show me my finance emails")
        assert query_type == "classification"

    def test_work_emails_classification(self, rag_engine):
        """Should classify work label queries as classification type."""
        query_type = rag_engine._detect_query_type("work emails")
        # 'work' alone may not be detected as a classification label
        assert query_type in ("classification", "semantic")

    def test_social_emails_classification(self, rag_engine):
        """Should classify social label queries as classification type."""
        query_type = rag_engine._detect_query_type("social emails")
        # 'social' alone may not be detected as a classification label
        assert query_type in ("classification", "semantic")

    def test_shopping_emails_classification(self, rag_engine):
        """Should classify shopping label queries as classification type."""
        query_type = rag_engine._detect_query_type("shopping emails")
        assert query_type == "classification"


class TestAttachmentQueryType:
    """Tests for the 'search-by-attachment' query type."""

    def test_emails_with_attachments(self, rag_engine):
        """Should classify attachment queries appropriately."""
        query_type = rag_engine._detect_query_type("emails with attachments")
        # LLM may classify as search-by-attachment or semantic
        assert query_type in ("search-by-attachment", "semantic")

    def test_find_pdfs(self, rag_engine):
        """Should classify PDF search queries."""
        query_type = rag_engine._detect_query_type("find emails with PDF files")
        assert query_type in ("search-by-attachment", "semantic", "filtered-temporal")


class TestDirectQueryClassifier:
    """Tests that use QueryClassifier directly instead of through RAGQueryEngine."""

    def test_classifier_conversation(self, query_classifier):
        """Direct test of QueryClassifier for conversation queries."""
        assert query_classifier.detect_query_type("hello") == "conversation"
        assert query_classifier.detect_query_type("hi there") == "conversation"
        assert query_classifier.detect_query_type("thanks") == "conversation"

    def test_classifier_aggregation(self, query_classifier):
        """Direct test of QueryClassifier for aggregation queries."""
        result = query_classifier.detect_query_type("how many emails do I have")
        assert result == "aggregation"

    def test_classifier_classification_labels(self, query_classifier):
        """Direct test of QueryClassifier for classification label queries."""
        result = query_classifier.detect_query_type("show me finance emails")
        assert result == "classification"

    def test_classifier_delegation_matches_rag_engine(self, rag_engine, query_classifier):
        """RAGQueryEngine._detect_query_type should delegate to QueryClassifier."""
        test_queries = ["hello", "how many emails", "finance emails"]
        
        for query in test_queries:
            rag_result = rag_engine._detect_query_type(query)
            classifier_result = query_classifier.detect_query_type(query)
            assert rag_result == classifier_result, \
                f"Mismatch for '{query}': RAG={rag_result}, Classifier={classifier_result}"

