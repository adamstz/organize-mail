"""Unit tests for chat history prompt functionality."""
import pytest
from unittest.mock import Mock, patch

from src.services.query_handlers.classification import ClassificationHandler
from src.services.llm_processor import LLMProcessor
from src.services.context_builder import ContextBuilder
from src.storage.memory_storage import InMemoryStorage


class TestChatHistoryPrompts:
    """Test chat history prompt extraction functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_storage = Mock()
        self.mock_llm = Mock()
        self.mock_context_builder = Mock()
        
        # Create handler instance
        self.handler = ClassificationHandler(
            storage=self.mock_storage,
            llm=self.mock_llm,
            context_builder=self.mock_context_builder
        )

    def test_classification_history_extraction_basic_followup(self):
        """Test basic follow-up scenario."""
        # Mock chat history
        chat_history = [
            {"role": "user", "content": "how many promotional emails do I have"},
            {"role": "assistant", "content": "You have 97 promotional emails"},
        ]
        
        # Mock LLM response for extraction - use _call_llm_simple
        with patch.object(self.handler, '_call_llm_simple', return_value="promotional"):
            # Mock _format_chat_history method
            self.handler._format_chat_history = Mock(return_value="User: how many promotional emails do I have\nAssistant: You have 97 promotional emails")
            
            # Test extraction
            result = self.handler._extract_label_from_history(chat_history)
            
            assert result == "promotions", f"Expected 'promotions', got '{result}'"

    def test_classification_history_extraction_topic_change(self):
        """Test topic change detection."""
        chat_history = [
            {"role": "user", "content": "show me job applications"},
            {"role": "assistant", "content": "I found 15 job applications"},
        ]
        
        with patch.object(self.handler, '_call_llm_simple', return_value="job"):
            self.handler._format_chat_history = Mock(return_value="User: show me job applications\nAssistant: I found 15 job applications")
            
            result = self.handler._extract_label_from_history(chat_history)
            
            # Should map to job-application via QUERY_TO_LABEL_MAPPING
            assert result == "job-application", f"Expected 'job-application', got '{result}'"

    def test_classification_history_extraction_multiple_topics(self):
        """Test multiple topics in history."""
        chat_history = [
            {"role": "user", "content": "how many receipts?"},
            {"role": "assistant", "content": "5 receipts"},
            {"role": "user", "content": "count spam emails"},
            {"role": "assistant", "content": "23 spam emails"},
        ]
        
        with patch.object(self.handler, '_call_llm_simple', return_value="receipt"):
            self.handler._format_chat_history = Mock(return_value="User: how many receipts?\nAssistant: 5 receipts\nUser: count spam emails\nAssistant: 23 spam emails")
            
            result = self.handler._extract_label_from_history(chat_history)
            
            assert result == "receipts", f"Expected 'receipts', got '{result}'"

    def test_classification_history_extraction_ambiguous_history(self):
        """Test ambiguous history handling."""
        chat_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
            {"role": "user", "content": "from those, what do you mean?"},
        ]
        
        with patch.object(self.handler, '_call_llm_simple', return_value="none"):
            self.handler._format_chat_history = Mock(return_value="User: hello\nAssistant: Hi! How can I help you?\nUser: from those, what do you mean?")
            
            result = self.handler._extract_label_from_history(chat_history)
            
            assert result is None, f"Expected None for ambiguous history, got '{result}'"

    def test_classification_history_extraction_empty_history(self):
        """Test empty history handling."""
        chat_history = []
        
        result = self.handler._extract_label_from_history(chat_history)
        
        assert result is None, f"Expected None for empty history, got '{result}'"

    def test_classification_history_extraction_llm_failure(self):
        """Test LLM failure handling."""
        chat_history = [
            {"role": "user", "content": "how many promotional emails?"},
            {"role": "assistant", "content": "You have 97 promotional emails"},
        ]
        
        # Mock LLM to raise exception
        self.mock_llm.invoke.side_effect = Exception("LLM failed")
        
        result = self.handler._extract_label_from_history(chat_history)
        
        assert result is None, f"Expected None on LLM failure, got '{result}'"

    def test_classification_history_extraction_prompt_formatting(self):
        """Test that history context is properly formatted."""
        chat_history = [
            {"role": "user", "content": "test query"},
            {"role": "assistant", "content": "test response"},
        ]
        
        # Mock _format_chat_history to verify it's called with correct data
        mock_formatter = Mock(return_value="Formatted history")
        self.handler._format_chat_history = mock_formatter
        
        with patch.object(self.handler, '_call_llm_simple', return_value="test"):
            self.handler._extract_label_from_history(chat_history)
            
            # Verify _format_chat_history was called with chat_history
            mock_formatter.assert_called_once_with(chat_history)

    def test_classification_history_mapping_integration(self):
        """Test integration with QUERY_TO_LABEL_MAPPING."""
        chat_history = [
            {"role": "user", "content": "how many promo emails?"},
            {"role": "assistant", "content": "5 promo emails"},
        ]
        
        with patch.object(self.handler, '_call_llm_simple', return_value="promotional"):
            self.handler._format_chat_history = Mock(return_value="Formatted history")
            
            result = self.handler._extract_label_from_history(chat_history)
            
            # Should use mapping: 'promotional' -> 'promotions'
            assert result == "promotions", f"Expected 'promotions' from mapping, got '{result}'"


if __name__ == "__main__":
    pytest.main([__file__])
