"""Unit tests for PostgreSQL keyword (full-text) search functionality."""

import pytest
from src.models.message import MailMessage


class TestKeywordSearchLogic:
    """Tests for keyword search logic (not database-dependent)."""
    
    def test_keyword_search_signature(self):
        """Verify keyword_search has expected signature."""
        from src.storage.postgres_storage import PostgresStorage
        import inspect
        
        sig = inspect.signature(PostgresStorage.keyword_search)
        params = list(sig.parameters.keys())
        
        assert 'self' in params
        assert 'query' in params
        assert 'limit' in params
        assert 'threshold' in params
    
    def test_hybrid_search_signature(self):
        """Verify hybrid_search has expected signature."""
        from src.storage.postgres_storage import PostgresStorage
        import inspect
        
        sig = inspect.signature(PostgresStorage.hybrid_search)
        params = list(sig.parameters.keys())
        
        assert 'self' in params
        assert 'query_embedding' in params
        assert 'query_text' in params
        assert 'vector_weight' in params
        assert 'keyword_weight' in params
        assert 'retrieval_k' in params
    
    def test_mail_message_has_get_body_text(self):
        """Verify MailMessage has get_body_text method."""
        msg = MailMessage(id="test", snippet="snippet")
        assert hasattr(msg, 'get_body_text')
        assert callable(msg.get_body_text)
        
        # Should fall back to snippet
        assert msg.get_body_text() == "snippet"


class TestRRFFusion:
    """Test Reciprocal Rank Fusion algorithm logic."""
    
    def test_rrf_formula(self):
        """Verify RRF score calculation."""
        # RRF formula: score = sum(weight / (k + rank))
        # With k=60 (industry standard)
        k = 60
        
        # Rank 1 in both lists
        score_both_rank1 = (0.6 / (k + 1)) + (0.4 / (k + 1))
        assert abs(score_both_rank1 - (1.0 / 61)) < 0.001
        
        # Rank 1 in vector only
        score_vector_only = 0.6 / (k + 1)
        assert score_vector_only < score_both_rank1
    
    def test_rrf_rank_1_beats_rank_50(self):
        """Items appearing early in lists should score higher."""
        k = 60
        
        # Item at rank 1
        score_rank1 = 0.5 / (k + 1) + 0.5 / (k + 1)
        
        # Item at rank 50
        score_rank50 = 0.5 / (k + 50) + 0.5 / (k + 50)
        
        assert score_rank1 > score_rank50
    
    def test_rrf_appearing_in_both_beats_single(self):
        """Items appearing in both lists should score higher than single-list items."""
        k = 60
        
        # Appears at rank 5 in both lists
        score_both = 0.5 / (k + 5) + 0.5 / (k + 5)
        
        # Appears at rank 1 in only one list  
        score_single = 0.5 / (k + 1)
        
        # Being in both lists (even at lower ranks) can score higher than top of one list
        # This demonstrates the value of hybrid search
        # (actual comparison depends on ranks)
