"""Handler for semantic (content-based) queries using vector search."""
from typing import Dict, Optional
import logging

from .base import QueryHandler
from ..prompt_templates import SEMANTIC_SEARCH_PROMPT

logger = logging.getLogger(__name__)


class SemanticHandler(QueryHandler):
    """Handle content-based queries using semantic/vector search."""

    def handle(self, question: str, limit: int = 5, threshold: float = 0.5, chat_history: Optional[list] = None) -> Dict:
        """Handle a semantic search query.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve
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

        if is_counting_query:
            original_limit = limit
            original_threshold = threshold
            limit = max(limit, 50)
            threshold = min(threshold, 0.25)
            logger.debug(
                "[SEMANTIC QUERY] Counting query - limit: %s->%s, threshold: %s->%s",
                original_limit, limit, original_threshold, threshold
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

        # Step 2: Retrieve similar emails
        logger.debug("[SEMANTIC QUERY] Searching for similar emails (limit=%s, threshold=%s)", limit, threshold)
        try:
            similar_emails = self.storage.similarity_search(
                query_embedding=question_embedding,
                limit=limit,
                threshold=threshold
            )
        except Exception as e:
            logger.debug("[SEMANTIC QUERY] Similarity search failed: %s", e)
            return self._build_response(
                answer=f"Failed to search emails due to database error: {str(e)}",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        if not similar_emails:
            logger.debug("[SEMANTIC QUERY] No similar emails found with threshold=%s", threshold)
            return self._build_response(
                answer="I couldn't find any relevant emails to answer your question.",
                sources=[],
                question=question,
                query_type='semantic',
                confidence='none',
            )

        # Log similarity scores for debugging
        logger.debug("[SEMANTIC QUERY] Top similarity scores:")
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
