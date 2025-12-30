"""Handler for semantic (content-based) queries using vector search."""
from typing import Dict, Optional, List, Tuple
import logging

from .base import QueryHandler
from ..prompt_templates import SEMANTIC_SEARCH_PROMPT

logger = logging.getLogger(__name__)


# Lazy load cross-encoder for reranking (only when needed)
_cross_encoder = None


def get_cross_encoder():
    """Lazy-load cross-encoder model for reranking."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            # Use a lightweight cross-encoder model for reranking
            _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            logger.info("[SEMANTIC] Loaded cross-encoder model for reranking")
        except Exception as e:
            logger.warning(f"[SEMANTIC] Failed to load cross-encoder: {e}. Falling back to no reranking.")
            _cross_encoder = False  # Mark as failed to avoid repeated attempts
    return _cross_encoder if _cross_encoder is not False else None


class SemanticHandler(QueryHandler):
    """Handle content-based queries using semantic/vector search."""

    def _rerank_results(
        self,
        question: str,
        results: List[Tuple],
        top_k: int = 5
    ) -> List[Tuple]:
        """Rerank retrieval results using cross-encoder for better relevance.
        
        Args:
            question: User's query
            results: List of (message, score) tuples from initial retrieval
            top_k: Number of top results to return after reranking
            
        Returns:
            Reranked list of (message, new_score) tuples
        """
        cross_encoder = get_cross_encoder()
        if cross_encoder is None or len(results) <= 1:
            # No reranking available or not enough results
            return results[:top_k]
        
        try:
            # Prepare query-document pairs for cross-encoder
            pairs = []
            for message, _ in results:
                # Create searchable text from message
                doc_text = f"{message.subject or ''} {message.snippet or ''}"
                pairs.append([question, doc_text])
            
            # Get cross-encoder scores
            scores = cross_encoder.predict(pairs)
            
            # Combine with original results and sort by cross-encoder score
            reranked = [
                (message, float(score))
                for (message, _), score in zip(results, scores)
            ]
            reranked.sort(key=lambda x: x[1], reverse=True)
            
            logger.debug(f"[SEMANTIC] Reranked {len(results)} results to top {top_k}")
            return reranked[:top_k]
            
        except Exception as e:
            logger.warning(f"[SEMANTIC] Reranking failed: {e}. Using original results.")
            return results[:top_k]

    def handle(self, question: str, limit: int = 5, threshold: float = 0.5, chat_history: Optional[list] = None) -> Dict:
        """Handle a semantic search query with hybrid search and reranking.

        Args:
            question: User's question
            limit: Final number of emails to return (after reranking)
            threshold: Minimum similarity threshold
            chat_history: Optional list of previous messages for context

        Returns:
            Query result with answer and sources
        """
        logger.info(f"[SEMANTIC QUERY] Processing semantic query (model: {self.llm.provider}/{self.llm.model})")

        if not self.embedder:
            return self._build_response(
                answer="Semantic search is not available - embedding service not configured.",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Check if this is a counting query - if so, search more emails
        question_lower = question.lower()
        is_counting_query = any(word in question_lower for word in ['how many', 'count', 'number of'])

        # Use higher retrieval_k for initial search, then rerank down to limit
        retrieval_k = 50  # Retrieve more candidates for better reranking
        if is_counting_query:
            retrieval_k = 100  # Even more for counting queries
            threshold = min(threshold, 0.25)
            logger.debug(
                "[SEMANTIC QUERY] Counting query - retrieval_k: %s, threshold: %s",
                retrieval_k, threshold
            )

        # Step 1: Embed the question
        logger.debug("[SEMANTIC QUERY] Generating embedding for question")
        try:
            question_embedding = self.embedder.embed_text(question)
        except Exception as e:
            logger.debug("[SEMANTIC QUERY] Embedding failed: %s", e)
            return self._build_response(
                answer=f"Failed to process your question due to embedding error: {str(e)}",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Step 2: Hybrid search (vector + keyword with RRF fusion)
        logger.debug("[SEMANTIC QUERY] Running hybrid search (retrieval_k=%s, threshold=%s)", retrieval_k, threshold)
        try:
            # Use hybrid search if available, fallback to pure vector search
            if hasattr(self.storage, 'hybrid_search'):
                similar_emails = self.storage.hybrid_search(
                    query_embedding=question_embedding,
                    query_text=question,
                    limit=limit,  # Final limit after fusion
                    retrieval_k=retrieval_k,  # Initial retrieval from each method
                    vector_weight=0.6,  # Slightly favor semantic search
                    keyword_weight=0.4
                )
                logger.debug("[SEMANTIC QUERY] Hybrid search returned %d results", len(similar_emails))
            else:
                # Fallback to pure vector search
                logger.debug("[SEMANTIC QUERY] Hybrid search not available, using pure vector search")
                similar_emails = self.storage.similarity_search(
                    query_embedding=question_embedding,
                    limit=retrieval_k,
                    threshold=threshold
                )
                # Rerank the vector results
                similar_emails = self._rerank_results(question, similar_emails, top_k=limit)
                logger.debug("[SEMANTIC QUERY] Vector search + rerank returned %d results", len(similar_emails))
                
        except Exception as e:
            logger.debug("[SEMANTIC QUERY] Search failed: %s", e)
            return self._build_response(
                answer=f"Failed to search emails due to database error: {str(e)}",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        if not similar_emails:
            logger.debug("[SEMANTIC QUERY] No similar emails found")
            return self._build_response(
                answer="I couldn't find any relevant emails to answer your question.",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Log similarity scores for debugging
        logger.debug("[SEMANTIC QUERY] Top results after hybrid search/reranking:")
        for i, (email, score) in enumerate(similar_emails[:5]):
            logger.debug(
                "[SEMANTIC QUERY]   %d. Score: %.3f - Subject: '%s...'",
                i + 1, score, email.subject[:50] if email.subject else ''
            )

        # Step 3: Build context from retrieved emails
        logger.debug("[SEMANTIC QUERY] Building context from %d emails", len(similar_emails))
        try:
            context = self.context_builder.build_context(similar_emails)
        except Exception as e:
            logger.debug("[SEMANTIC QUERY] Context building failed: %s", e)
            return self._build_response(
                answer=f"Failed to build context from emails: {str(e)}",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Step 4: Generate answer using LLM
        logger.debug("[SEMANTIC QUERY] Generating answer with LLM")
        try:
            answer = self._generate_answer(question, context, chat_history)
        except Exception as e:
            logger.debug("[SEMANTIC QUERY] Answer generation failed: %s", e)
            return self._build_response(
                answer=f"Failed to generate answer: {str(e)}",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Format sources with similarity scores
        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': float(score),
                'date': msg.internal_date,
            }
            for msg, score in similar_emails
        ]

        # Determine confidence based on top similarity score
        top_score = similar_emails[0][1]
        if top_score > 0.8:
            confidence = 'high'
        elif top_score > 0.6:
            confidence = 'medium'
        else:
            confidence = 'low'

        logger.debug("[SEMANTIC QUERY] Query completed with confidence: %s", confidence)

        return self._build_response(
            answer=answer,
            sources=sources,
            question=question,
            query_type='semantic',
            confidence=confidence,
        )

    def _generate_answer(self, question: str, context: str, chat_history: Optional[list] = None) -> str:
        """Generate answer using LLM with email context."""
        # Format chat history for context
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        # Create enhanced prompt with chat history
        enhanced_prompt = SEMANTIC_SEARCH_PROMPT.format(
            context=context,
            question=question,
        ) + history_context

        return self._call_llm(enhanced_prompt)
