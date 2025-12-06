"""Handler for search-by-sender queries."""
from typing import Dict
import logging

from .base import QueryHandler
from ..prompt_templates import SEARCH_BY_SENDER_PROMPT, SENDER_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class SenderHandler(QueryHandler):
    """Handle search queries for emails from a specific sender."""

    def handle(self, question: str, limit: int = 5) -> Dict:
        """Handle a search-by-sender query.

        Args:
            question: User's question
            limit: Maximum number of emails to return

        Returns:
            Query result with emails from sender
        """
        logger.info("[SEARCH BY SENDER] Processing sender search")

        # Extract sender from question
        try:
            sender = self._extract_sender(question)
            logger.debug("[SEARCH BY SENDER] Extracted sender: %s", sender)
        except Exception as e:
            logger.debug("[SEARCH BY SENDER] Failed to extract sender: %s", e)
            return self._build_response(
                answer="I couldn't determine which sender you're looking for. Please be more specific.",
                sources=[],
                question=question,
                query_type='search-by-sender',
                confidence='none',
            )

        # Query database
        emails = self.storage.search_by_sender(sender, limit=limit)

        if not emails:
            return self._build_response(
                answer=f"I couldn't find any emails from '{sender}'.",
                sources=[],
                question=question,
                query_type='search-by-sender',
                confidence='none',
            )

        # Build context and generate answer
        context = self.context_builder.build_context_from_messages(emails)
        answer = self._generate_answer(question, context, sender)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(emails),
            question=question,
            query_type='search-by-sender',
            confidence='high',
        )

    def _extract_sender(self, question: str) -> str:
        """Extract sender name/email from the question.

        Raises ValueError if extraction fails.
        """
        prompt = SENDER_EXTRACTION_PROMPT.format(question=question)
        response = self._call_llm_simple(prompt).strip()

        # Clean up
        sender = response.strip('"').strip("'").strip('.').strip(',')

        # Remove common prefixes that might leak in
        for prefix in ['the sender is', 'sender:', 'sender is', 'the']:
            if sender.lower().startswith(prefix):
                sender = sender[len(prefix):].strip()

        # Validate we got something reasonable
        if len(sender) < 2 or sender.lower() in ['the', 'a', 'an', 'my', 'show', 'all']:
            raise ValueError(f"Invalid sender extracted: '{sender}'")

        return sender

    def _generate_answer(self, question: str, context: str, sender: str) -> str:
        """Generate answer using the LLM with sender context."""
        prompt = SEARCH_BY_SENDER_PROMPT.format(
            sender=sender,
            context=context,
            question=question,
        )
        return self._call_llm(prompt)
