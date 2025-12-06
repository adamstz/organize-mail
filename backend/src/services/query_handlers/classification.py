"""Handler for classification-based queries."""
from typing import Dict
import logging

from .base import QueryHandler
from ..prompt_templates import CLASSIFICATION_QUERY_PROMPT
from ...classification_labels import get_label_from_query

logger = logging.getLogger(__name__)


class ClassificationHandler(QueryHandler):
    """Handle queries based on email classification labels."""

    def handle(self, question: str, limit: int = 5) -> Dict:
        """Handle a classification-based query.

        Args:
            question: User's question
            limit: Maximum number of emails to include in context

        Returns:
            Query result with answer and sources
        """
        logger.info("[CLASSIFICATION] Processing classification query")

        # Get the matched label from the query
        matched_label = get_label_from_query(question)

        if not matched_label:
            # Fallback to indicating no label found
            return self._build_response(
                answer="I couldn't determine which classification label you're asking about.",
                sources=[],
                question=question,
                query_type='classification',
                confidence='none',
            )

        # Get all emails with this label
        emails, total_count = self.storage.list_messages_by_label(
            matched_label, limit=limit, offset=0
        )

        if not emails:
            return self._build_response(
                answer=f"I couldn't find any emails with the label '{matched_label}' in the database.",
                sources=[],
                question=question,
                query_type='classification',
                confidence='none',
            )

        # Build context from labeled emails
        context = self.context_builder.build_context_from_messages(emails)

        # Generate answer using LLM with classification context
        answer = self._generate_answer(question, context, emails, total_count, matched_label)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(emails),
            question=question,
            query_type='classification',
            confidence='high',
            total_count=total_count,
        )

    def _generate_answer(
        self,
        question: str,
        context: str,
        emails: list,
        total_count: int,
        label: str
    ) -> str:
        """Generate answer for classification queries using LLM."""
        prompt = CLASSIFICATION_QUERY_PROMPT.format(
            label=label,
            total_count=total_count,
            sample_count=len(emails),
            context=context,
            question=question,
        )
        return self._call_llm(prompt)
