"""Handler for search-by-sender queries."""
from typing import Dict, Optional
import logging
import re

from .base import QueryHandler
from ..prompt_templates import SEARCH_BY_SENDER_PROMPT, SENDER_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class SenderHandler(QueryHandler):
    """Handle search queries for emails from a specific sender."""

    def handle(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle a search-by-sender query.

        Args:
            question: User's question
            limit: Maximum number of emails to return
            chat_history: Optional list of previous messages for context

        Returns:
            Query result with emails from sender
        """
        logger.info(f"[SEARCH BY SENDER] Processing sender search (model: {self.llm.provider}/{self.llm.model})")

        # Extract number from query if specified (e.g., "last 10", "show 20")
        requested_limit = self._extract_number_from_query(question)
        if requested_limit:
            limit = requested_limit
            logger.info(f"[SEARCH BY SENDER] Extracted limit from query: {limit}")

        # Extract sender from question (considering chat history for pronoun resolution)
        try:
            sender = self._extract_sender(question, chat_history)
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

        # Build context and generate answer (include chat history for context)
        context = self.context_builder.build_context_from_messages(emails)
        answer = self._generate_answer(question, context, sender, chat_history)

        return self._build_response(
            answer=answer,
            sources=self._format_sources(emails),
            question=question,
            query_type='search-by-sender',
            confidence='high',
        )

    def _extract_sender(self, question: str, chat_history: Optional[list] = None) -> str:
        """Extract sender name/email from the question.

        Args:
            question: Current question
            chat_history: Previous conversation for context (helps with pronouns like "them")

        Raises ValueError if extraction fails.
        """
        logger.info("[SENDER HANDLER] ========== Extracting Sender ==========")
        logger.info("[SENDER HANDLER] Question: '%s'", question)
        
        # If there's chat history, include it for pronoun resolution
        history_context = self._format_chat_history(chat_history) if chat_history else ""
        if history_context:
            logger.debug("[SENDER HANDLER] Using chat history context: %s", history_context[:100])

        prompt = SENDER_EXTRACTION_PROMPT.format(question=question) + history_context
        logger.info("[SENDER HANDLER] Extraction prompt:\n%s", prompt)
        
        response = self._call_llm_simple(prompt).strip()
        logger.info("[SENDER HANDLER] Raw LLM response: '%s'", response)

        # Clean up
        sender = response.strip('"').strip("'").strip('.').strip(',')
        logger.debug("[SENDER HANDLER] After initial cleanup: '%s'", sender)

        # Remove common prefixes that might leak in
        for prefix in ['the sender is', 'sender:', 'sender is', 'the']:
            if sender.lower().startswith(prefix):
                sender = sender[len(prefix):].strip()
                logger.debug("[SENDER HANDLER] Removed prefix '%s': '%s'", prefix, sender)

        # Validate we got something reasonable
        if len(sender) < 2 or sender.lower() in ['the', 'a', 'an', 'my', 'show', 'all']:
            logger.error("[SENDER HANDLER] Invalid sender extracted: '%s'", sender)
            raise ValueError(f"Invalid sender extracted: '{sender}'")

        logger.info("[SENDER HANDLER] ✓ Final extracted sender: '%s'", sender)
        return sender

    def _generate_answer(self, question: str, context: str, sender: str, chat_history: Optional[list] = None) -> str:
        """Generate answer using the LLM with sender context."""
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        prompt = SEARCH_BY_SENDER_PROMPT.format(
            sender=sender,
            context=context,
            question=question,
        ) + history_context
        return self._call_llm(prompt)

    def _extract_number_from_query(self, question: str) -> Optional[int]:
        """Extract number from query like 'last 10 emails' or 'show 20 messages'.

        Args:
            question: User's question

        Returns:
            Extracted number or None if not found
        """
        # Look for patterns like "last N", "show N", "N emails", "N messages"
        patterns = [
            r'\b(?:last|recent|latest)\s+(\d+)\b',
            r'\b(?:show|get|find)\s+(?:me\s+)?(\d+)\b',
            r'\b(\d+)\s+(?:emails?|messages?|mails?)\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                # Sanity check: limit to reasonable range
                if 1 <= num <= 100:
                    return num

        return None
