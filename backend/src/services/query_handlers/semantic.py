"""Handler for semantic (content-based) queries using vector search."""
from typing import Dict, List
import logging

from .base import QueryHandler
from ..prompt_templates import SEMANTIC_SEARCH_PROMPT

logger = logging.getLogger(__name__)


class SemanticHandler(QueryHandler):
    """Handle content-based queries using semantic/vector search."""

    def handle(self, question: str, limit: int = 5, threshold: float = 0.5) -> Dict:
        """Handle a semantic search query.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve
            threshold: Minimum similarity threshold

        Returns:
            Query result with answer and sources
        """
        logger.info("[SEMANTIC QUERY] Processing semantic query")

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
            answer = self._generate_answer(question, context)
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

    def find_similar_emails(self, message_id: str, limit: int = 5) -> List[Dict]:
        """Find emails similar to a given email.

        Args:
            message_id: ID of the email to find similar emails for
            limit: Number of similar emails to return

        Returns:
            List of similar email metadata with similarity scores
        """
        # Get the email
        message = self.storage.get_message_by_id(message_id)
        if not message:
            return []

        # Get its embedding from database
        conn = self.storage.connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT embedding FROM messages WHERE id = %s AND embedding IS NOT NULL",
            (message_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return []

        embedding = row[0]

        # Search for similar (excluding the original)
        similar_emails = self.storage.similarity_search(
            query_embedding=embedding,
            limit=limit + 1,
            threshold=0.5
        )

        # Filter out the original email
        similar_emails = [(msg, score) for msg, score in similar_emails if msg.id != message_id]

        # Format results
        return [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': float(score),
                'date': msg.internal_date,
                'labels': msg.classification_labels or []
            }
            for msg, score in similar_emails[:limit]
        ]

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using LLM with email context."""
        prompt = SEMANTIC_SEARCH_PROMPT.format(
            context=context,
            question=question,
        )
        return self._call_llm(prompt)
