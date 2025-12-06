"""Handler for search-by-attachment queries."""
from typing import Dict
import logging

from .base import QueryHandler
from ..prompt_templates import SEARCH_BY_ATTACHMENT_PROMPT

logger = logging.getLogger(__name__)


class AttachmentHandler(QueryHandler):
    """Handle search queries for emails with attachments."""

    def handle(self, question: str, limit: int = 5) -> Dict:
        """Handle a search-by-attachment query.

        Args:
            question: User's question
            limit: Maximum number of emails to return

        Returns:
            Query result with emails that have attachments
        """
        logger.info("[SEARCH BY ATTACHMENT] Processing attachment search")

        # Query database for emails with attachments
        emails = self.storage.search_by_attachment(limit=limit)

        if not emails:
            return self._build_response(
                answer="I couldn't find any emails with attachments.",
                sources=[],
                question=question,
                query_type='search-by-attachment',
                confidence='none',
            )

        # Build context and generate answer
        context = self.context_builder.build_context_from_messages(emails)
        answer = self._generate_answer(question, context)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(emails),
            question=question,
            query_type='search-by-attachment',
            confidence='high',
        )

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using the LLM with attachment context."""
        prompt = SEARCH_BY_ATTACHMENT_PROMPT.format(
            context=context,
            question=question,
        )
        return self._call_llm(prompt)
