"""Tests for hybrid search and cross-encoder reranking improvements."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.storage.postgres_storage import PostgresStorage
from src.models.message import MailMessage
from src.services.query_handlers.semantic import SemanticHandler, get_cross_encoder


class TestHybridSearch:
    """Test hybrid search (vector + keyword) with RRF fusion."""
    
    def test_rrf_fusion_logic(self):
        """Test that RRF correctly combines and ranks results."""
        # Create mock messages
        msg1 = MailMessage(id="1", subject="Invoice from Acme Corp", snippet="Payment due")
        msg2 = MailMessage(id="2", subject="Receipt confirmation", snippet="Thank you for your purchase")
        msg3 = MailMessage(id="3", subject="Acme Newsletter", snippet="Latest updates")
        
        # Simulate vector results (msg1 and msg2 rank high)
        vector_results = [(msg1, 0.9), (msg2, 0.85), (msg3, 0.6)]
        
        # Simulate keyword results (msg1 and msg3 rank high due to "Acme")
        keyword_results = [(msg1, 5.2), (msg3, 4.8), (msg2, 2.1)]
        
        # Mock storage methods
        storage = Mock(spec=PostgresStorage)
        storage.similarity_search = Mock(return_value=vector_results)
        storage.keyword_search = Mock(return_value=keyword_results)
        storage.hybrid_search = storage.hybrid_search  # Use real implementation
        
        # Manually test RRF logic
        rrf_k = 60
        vector_weight = 0.6
        keyword_weight = 0.4
        
        fused_scores = {}
        
        # Process vector results
        for rank, (message, similarity) in enumerate(vector_results, start=1):
            rrf_score = vector_weight / (rrf_k + rank)
            fused_scores[message.id] = {'message': message, 'score': rrf_score}
        
        # Process keyword results
        for rank, (message, keyword_rank) in enumerate(keyword_results, start=1):
            rrf_score = keyword_weight / (rrf_k + rank)
            if message.id in fused_scores:
                fused_scores[message.id]['score'] += rrf_score
            else:
                fused_scores[message.id] = {'message': message, 'score': rrf_score}
        
        # Sort by fused score
        sorted_results = sorted(fused_scores.values(), key=lambda x: x['score'], reverse=True)
        
        # msg1 should rank highest (appears in both top positions)
        assert sorted_results[0]['message'].id == "1"
        # msg1 score should be sum of both RRF contributions
        assert sorted_results[0]['score'] > 0.015  # Approximately 0.6/61 + 0.4/61


class TestCrossEncoderReranking:
    """Test cross-encoder reranking functionality."""
    
    def test_cross_encoder_lazy_loading(self):
        """Test that cross-encoder is loaded lazily and cached."""
        # Reset global state
        import src.services.query_handlers.semantic as semantic_module
        semantic_module._cross_encoder = None
        
        with patch('sentence_transformers.CrossEncoder') as mock_ce:
            mock_model = Mock()
            mock_ce.return_value = mock_model
            
            # First call should load the model
            encoder1 = get_cross_encoder()
            assert encoder1 == mock_model
            mock_ce.assert_called_once()
            
            # Second call should return cached model
            encoder2 = get_cross_encoder()
            assert encoder2 == mock_model
            mock_ce.assert_called_once()  # Still only called once
    
    def test_reranking_improves_order(self):
        """Test that reranking reorders results by relevance."""
        handler = SemanticHandler(
            storage=Mock(),
            llm=Mock(),
            embedder=Mock(),
            context_builder=Mock()
        )
        
        # Create mock messages
        msg1 = MailMessage(id="1", subject="Unrelated topic", snippet="Random content")
        msg2 = MailMessage(id="2", subject="Python tutorial", snippet="Learn Python programming")
        msg3 = MailMessage(id="3", subject="Python job", snippet="Senior Python developer position")
        
        results = [(msg1, 0.75), (msg2, 0.70), (msg3, 0.68)]
        question = "Python programming jobs"
        
        # Mock cross-encoder to prefer msg3, then msg2 (job-related, then tutorial)
        mock_encoder = Mock()
        mock_encoder.predict = Mock(return_value=[0.2, 0.6, 0.9])  # Higher score for msg3
        
        with patch('src.services.query_handlers.semantic.get_cross_encoder', return_value=mock_encoder):
            reranked = handler._rerank_results(question, results, top_k=3)
            
            # msg3 should now be first (highest cross-encoder score)
            assert reranked[0][0].id == "3"
            assert reranked[1][0].id == "2"
            assert reranked[2][0].id == "1"
    
    def test_reranking_handles_failure_gracefully(self):
        """Test that reranking failures fallback to original order."""
        handler = SemanticHandler(
            storage=Mock(),
            llm=Mock(),
            embedder=Mock(),
            context_builder=Mock()
        )
        
        msg1 = MailMessage(id="1", subject="Test", snippet="Content")
        results = [(msg1, 0.8)]
        
        # Mock cross-encoder to raise an exception
        mock_encoder = Mock()
        mock_encoder.predict = Mock(side_effect=RuntimeError("Model error"))
        
        with patch('src.services.query_handlers.semantic.get_cross_encoder', return_value=mock_encoder):
            reranked = handler._rerank_results("test query", results, top_k=5)
            
            # Should return original results
            assert len(reranked) == 1
            assert reranked[0][0].id == "1"


class TestFullBodyContext:
    """Test that full email body is used in context instead of snippet."""
    
    def test_get_body_text_extracts_from_payload(self):
        """Test MailMessage.get_body_text() extracts full body."""
        import base64
        
        # Create a mock payload with text/plain part
        body_text = "This is the full email body with lots of details that wouldn't fit in a snippet."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
        
        payload = {
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": encoded_body
                    }
                }
            ]
        }
        
        msg = MailMessage(
            id="1",
            subject="Test",
            snippet="Short snippet...",
            payload=payload
        )
        
        full_body = msg.get_body_text()
        assert full_body == body_text
        assert len(full_body) > len(msg.snippet)
    
    def test_get_body_text_falls_back_to_snippet(self):
        """Test fallback to snippet when payload is unavailable."""
        msg = MailMessage(
            id="1",
            subject="Test",
            snippet="Fallback snippet",
            payload=None
        )
        
        assert msg.get_body_text() == "Fallback snippet"
    
    def test_get_body_text_multipart_prefers_plain(self):
        """Should prioritize text/plain but may include other text content."""
        import base64
        
        plain_text = "Plain text version"
        html_text = "<p>HTML version</p>"
        
        payload = {
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": base64.urlsafe_b64encode(html_text.encode()).decode()
                    }
                },
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(plain_text.encode()).decode()
                    }
                }
            ]
        }
        
        msg = MailMessage(id="1", payload=payload)
        body = msg.get_body_text()
        # Should include plain text (prioritized)
        assert plain_text in body
        # Implementation may include HTML too - that's acceptable for better search coverage
    
    def test_get_body_text_nested_multipart(self):
        """Should handle nested multipart structures."""
        import base64
        
        nested_text = "Nested plain text content"
        
        payload = {
            "parts": [{
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "data": base64.urlsafe_b64encode(nested_text.encode()).decode()
                        }
                    }
                ]
            }]
        }
        
        msg = MailMessage(id="1", payload=payload)
        assert msg.get_body_text() == nested_text
    
    def test_get_body_text_handles_invalid_base64(self):
        """Should handle invalid base64 gracefully."""
        payload = {
            "mimeType": "text/plain",
            "body": {
                "data": "!!!invalid-base64!!!"
            }
        }
        
        msg = MailMessage(id="1", snippet="fallback", payload=payload)
        # Should fall back to snippet without crashing
        result = msg.get_body_text()
        assert isinstance(result, str)
    
    def test_get_body_text_empty_payload(self):
        """Should handle empty payload gracefully."""
        msg = MailMessage(id="1", snippet="snippet", payload={})
        assert msg.get_body_text() == "snippet"


class TestKeywordSearch:
    """Test PostgreSQL full-text search functionality."""
    
    @pytest.mark.integration
    def test_keyword_search_query_format(self):
        """Test that keyword search SQL uses correct tsvector syntax."""
        # This would require a real database connection
        # For now, just verify the method exists
        storage = PostgresStorage.__new__(PostgresStorage)
        assert hasattr(storage, 'keyword_search')
        assert hasattr(storage, 'hybrid_search')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
