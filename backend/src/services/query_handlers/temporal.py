"""Handler for temporal queries (time-based and filtered-temporal)."""
from typing import Dict, List, Optional
import logging

from .base import QueryHandler
from ..prompt_templates import TEMPORAL_QUERY_PROMPT, FILTERED_TEMPORAL_PROMPT, KEYWORD_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class TemporalHandler(QueryHandler):
    """Handle time-based queries, both pure temporal and filtered-temporal."""

    def handle(self, question: str, limit: int = 5, filtered: bool = False, chat_history: Optional[list] = None) -> Dict:
        """Handle a temporal query.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve
            filtered: If True, treat as filtered-temporal (time + content filter)
            chat_history: Optional list of previous messages for context

        Returns:
            Query result with answer and sources
        """
        if filtered:
            return self._handle_filtered(question, limit, chat_history)
        else:
            return self._handle_pure_temporal(question, limit, chat_history)

    def handle_filtered(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle a filtered-temporal query (time + content filter).

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve
            chat_history: Optional list of previous messages for context

        Returns:
            Query result with answer and sources
        """
        return self._handle_filtered(question, limit, chat_history)

    def _handle_pure_temporal(self, question: str, limit: int, chat_history: Optional[list] = None) -> Dict:
        """Handle pure temporal queries without content filtering."""
        logger.info(f"[TEMPORAL] Processing pure temporal query (model: {self.llm.provider}/{self.llm.model})")

        # Get recent emails directly from database (sorted by date)
        recent_emails = self.storage.list_messages(limit=limit, offset=0)

        if not recent_emails:
            return self._build_response(
                answer="I couldn't find any emails in the database.",
                sources=[],
                question=question,
                query_type='temporal',
                confidence='none',
            )

        # Build context from recent emails
        context = self.context_builder.build_context_from_messages(recent_emails)

        # Generate answer using LLM with temporal context
        answer = self._generate_temporal_answer(question, context, chat_history)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(recent_emails),
            question=question,
            query_type='temporal',
            confidence='high',
        )

    def _handle_filtered(self, question: str, limit: int, chat_history: Optional[list] = None) -> Dict:
        """Handle temporal queries with content filtering."""
        logger.info(
            f"[FILTERED TEMPORAL] Processing query with content + temporal filtering "
            f"(model: {self.llm.provider}/{self.llm.model})"
        )

        # Extract keywords from the question
        keywords = self._extract_keywords(question)

        if not keywords:
            logger.debug("[FILTERED TEMPORAL] No keywords found, falling back to temporal")
            return self._handle_pure_temporal(question, limit, chat_history)

        logger.debug("[FILTERED TEMPORAL] Searching with keywords: %s", keywords)

        # Query database with keyword filtering
        emails = self.storage.search_by_keywords(keywords, limit=limit)

        if not emails:
            logger.debug("[FILTERED TEMPORAL] No emails found matching keywords")
            return self._build_response(
                answer=f"I couldn't find any emails matching '{', '.join(keywords)}' in the database.",
                sources=[],
                question=question,
                query_type='filtered-temporal',
                confidence='none',
            )

        logger.debug("[FILTERED TEMPORAL] Found %d matching emails", len(emails))

        # Build context from filtered emails
        context = self.context_builder.build_context_from_messages(emails)

        # Generate answer using LLM
        answer = self._generate_filtered_answer(question, context, keywords, chat_history)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(emails),
            question=question,
            query_type='filtered-temporal',
            confidence='high',
        )

    def _extract_keywords(self, question: str) -> List[str]:
        """Extract search keywords from the question using LLM.

        Returns empty list if extraction fails.
        """
        try:
            prompt = KEYWORD_EXTRACTION_PROMPT.format(question=question)
            keywords_str = self._call_llm_simple(prompt).strip().lower()

            # Clean up the response
            keywords_str = self._clean_keywords_response(keywords_str)

            # Parse comma-separated or newline-separated keywords
            keywords = []
            for k in keywords_str.replace('\n', ',').split(','):
                k = k.strip().strip('"').strip("'").strip('-').strip('*').strip(':').strip()
                if k and len(k) > 2 and k not in ['the', 'and', 'or']:
                    keywords.append(k)

            # Remove duplicates while preserving order
            keywords = list(dict.fromkeys(keywords))[:3]  # Max 3 keywords
            logger.debug("[FILTERED TEMPORAL] LLM extracted keywords: %s", keywords)
            return keywords

        except Exception as e:
            logger.debug("[FILTERED TEMPORAL] Failed to extract keywords via LLM (%s), using fallback", e)
            return self._extract_keywords_fallback(question)

    def _clean_keywords_response(self, keywords_str: str) -> str:
        """Clean up verbose LLM responses for keyword extraction."""
        for prefix in [
            'sure', 'here are', 'keywords:', 'the keywords', 'extracted',
            'from', 'email query', 'are:', '-', '*', '•', ':',
        ]:
            keywords_str = keywords_str.replace(prefix, '')
        return keywords_str

    def _extract_keywords_fallback(self, question: str) -> List[str]:
        """Extract keywords using simple word filtering."""
        question_lower = question.lower()
        common_words = {
            'the', 'my', 'me', 'show', 'get', 'find', 'what', 'are', 'is', 'from',
            'about', 'recent', 'latest', 'last', 'most', 'five', 'ten', 'emails',
            'messages', 'mails',
        }
        keywords = [
            word for word in question_lower.split()
            if word not in common_words and len(word) > 3
        ]
        logger.debug("[FILTERED TEMPORAL] Fallback keywords: %s", keywords)
        return keywords[:3]

    def _generate_temporal_answer(self, question: str, context: str, chat_history: Optional[list] = None) -> str:
        """Generate answer for pure temporal queries."""
        # Format chat history for context
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        # Create enhanced prompt with chat history
        enhanced_prompt = TEMPORAL_QUERY_PROMPT.format(
            context=context,
            question=question,
        ) + history_context

        return self._call_llm(enhanced_prompt)

    def _generate_filtered_answer(self, question: str, context: str, keywords: List[str], chat_history: Optional[list] = None) -> str:
        """Generate answer for filtered-temporal queries."""
        # Format chat history for context
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        # Create enhanced prompt with chat history
        enhanced_prompt = FILTERED_TEMPORAL_PROMPT.format(
            keywords=', '.join(keywords),
            context=context,
            question=question,
        ) + history_context

        return self._call_llm(enhanced_prompt)
