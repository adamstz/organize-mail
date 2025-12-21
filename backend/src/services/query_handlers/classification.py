"""Handler for classification-based queries."""
from typing import Dict, Optional
import logging

from .base import QueryHandler
from ..prompt_templates import CLASSIFICATION_QUERY_PROMPT, CLASSIFICATION_HISTORY_EXTRACTION_PROMPT
from ...classification_labels import get_label_from_query

logger = logging.getLogger(__name__)


class ClassificationHandler(QueryHandler):
    """Handle queries based on email classification labels."""

    def handle(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle a classification-based query.

        Args:
            question: User's question
            limit: Maximum number of emails to include in context
            chat_history: Optional previous conversation for context

        Returns:
            Query result with answer and sources
        """
        logger.info(f"[CLASSIFICATION] Processing classification query (model: {self.llm.provider}/{self.llm.model})")

        # Get the matched label from query
        matched_label = get_label_from_query(question)

        # If no direct match found, try to extract from chat history
        if not matched_label and chat_history:
            matched_label = self._extract_label_from_history(chat_history)
            logger.info(f"[CLASSIFICATION] Extracted label from history: '{matched_label}'")

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

    def _extract_label_from_history(self, chat_history: list) -> str | None:
        """Extract classification label from chat history using LLM.

        Args:
            chat_history: Previous conversation messages

        Returns:
            Classification label string or None if not found
        """
        # Format chat history for context
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        # Use LLM to extract the classification topic from history
        extraction_prompt = CLASSIFICATION_HISTORY_EXTRACTION_PROMPT.format(
            history_context=history_context
        )

        try:
            extracted_label = self._call_llm_simple(extraction_prompt).strip().lower()

            # Clean up the response
            if extracted_label == "none" or len(extracted_label) < 2:
                return None

            # Map common variations to exact labels using existing system
            from ...classification_labels import QUERY_TO_LABEL_MAPPING

            # Apply mapping if available
            final_label = QUERY_TO_LABEL_MAPPING.get(extracted_label, extracted_label)
            logger.info(f"[CLASSIFICATION] LLM extracted '{extracted_label}' -> mapped to '{final_label}'")
            return final_label

        except Exception as e:
            logger.debug(f"[CLASSIFICATION] Failed to extract label from history: {e}")
            return None
