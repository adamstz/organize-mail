"""Handler for aggregation/statistical queries."""
from typing import Dict
import logging

from .base import QueryHandler
from ..prompt_templates import TOPIC_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class AggregationHandler(QueryHandler):
    """Handle aggregation and statistical queries."""

    def handle(self, question: str, limit: int = 5) -> Dict:
        """Handle an aggregation query.

        Args:
            question: User's question
            limit: Not typically used for aggregation

        Returns:
            Query result with statistical answer
        """
        logger.info("[AGGREGATION] Processing aggregation query")

        question_lower = question.lower()

        # Check if this is a "how many [topic]" query
        if 'how many' in question_lower and not any(word in question_lower for word in ['total', 'per day', 'unread']):
            result = self._handle_topic_count(question, question_lower)
            if result:
                return result
            # Fall through to standard aggregation if topic extraction fails

        # Handle different types of aggregation queries
        if 'per day' in question_lower or 'daily' in question_lower:
            return self._handle_daily_stats(question)
        elif 'how many' in question_lower and ('unread' in question_lower or 'not read' in question_lower):
            return self._handle_unread_count(question)
        elif 'how many' in question_lower or 'total' in question_lower:
            return self._handle_total_count(question)
        elif 'most common sender' in question_lower or 'who emails me most' in question_lower:
            return self._handle_top_senders(question)
        else:
            return self._handle_generic_aggregation(question)

    def _handle_topic_count(self, question: str, question_lower: str) -> Dict | None:
        """Handle counting emails by topic.

        Returns None if topic extraction fails.
        """
        try:
            topic = self._extract_topic(question)
            if not topic:
                return None

            count = self.storage.count_by_topic(topic)
            logger.debug("[AGGREGATION] Found %s emails matching '%s'", count, topic)

            answer = f"You have {count} emails related to '{topic}'."
            return self._build_response(
                answer=answer,
                sources=[],
                question=question,
                query_type='aggregation',
                confidence='high',
            )
        except Exception as e:
            logger.debug("[AGGREGATION] Failed to extract topic: %s", e)
            return None

    def _extract_topic(self, question: str) -> str | None:
        """Extract topic from a counting query using LLM.

        Returns None if extraction fails.
        """
        prompt = TOPIC_EXTRACTION_PROMPT.format(question=question)
        topic = self._call_llm_simple(prompt).strip()

        logger.debug("[AGGREGATION] Raw LLM response: '%s'", topic)

        # Clean up verbose LLM responses
        topic = self._clean_topic_response(topic)

        logger.debug("[AGGREGATION] Cleaned topic: '%s'", topic)

        # Validate we got something reasonable
        if len(topic) < 2 or len(topic) > 50:
            return None

        # Check for nonsense responses
        if any(word in topic.lower() for word in ['not provided', 'cannot', 'company/sender', 'context']):
            logger.debug("[AGGREGATION] LLM extraction failed, using keyword fallback")
            return self._extract_topic_fallback(question)

        return topic

    def _clean_topic_response(self, topic: str) -> str:
        """Clean up verbose LLM responses for topic extraction."""
        topic_lower = topic.lower()

        # Remove common verbose prefixes
        for phrase in [
            'sure, here\'s the topic/sender from the counting query:',
            'here\'s the topic/sender:',
            'the topic/sender is',
            'topic/sender:',
            'the topic is',
            'topic is',
            'sender is',
            'the sender is',
            'your answer (company name only):',
            'company name only:',
            'topic:',
            'sender:',
            'keywords:',
            'sure,',
            'here',
        ]:
            if topic_lower.startswith(phrase):
                topic = topic[len(phrase):].strip()
                topic_lower = topic.lower()

        # Remove markdown formatting
        topic = topic.replace('**', '').replace('*', '').replace('__', '').replace('_', '')

        # Remove quotes and punctuation
        topic = topic.strip('"').strip("'").strip('.').strip(',').strip(':').strip()

        # Handle multi-part responses
        if ':' in topic and len(topic.split(':')) == 2:
            _, value = topic.split(':', 1)
            topic = value.strip()

        # Filter verbose multi-word responses
        words = topic.split()
        if len(words) > 3:
            filtered_words = [
                w for w in words
                if w.lower() not in [
                    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'topic', 'sender',
                    'query', 'counting', 'email', 'emails', 'message', 'messages',
                    'mail', 'mails', 'from', 'to', 'about',
                ]
            ]
            if filtered_words:
                topic = " ".join(filtered_words[:3])

        return topic.strip()

    def _extract_topic_fallback(self, question: str) -> str | None:
        """Extract topic using simple keyword extraction."""
        question_lower = question.lower()
        words = question_lower.split()

        stop_words = {
            'how', 'many', 'do', 'i', 'have', 'mail', 'mails', 'email', 'emails',
            'message', 'messages', 'my', 'the', 'from', 'a', 'an', 'count'
        }
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        if keywords:
            topic = ' '.join(keywords[:3])
            logger.debug("[AGGREGATION] Fallback extracted topic: '%s'", topic)
            return topic
        return None

    def _handle_daily_stats(self, question: str) -> Dict:
        """Handle emails per day queries."""
        rows = self.storage.get_daily_email_stats(days=30)

        if rows:
            avg_per_day = sum(r['count'] for r in rows) / len(rows)
            answer = f"You receive an average of {avg_per_day:.1f} emails per day (based on the last 30 days)."
        else:
            answer = "I couldn't calculate email statistics."

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='aggregation',
            confidence='high',
        )

    def _handle_unread_count(self, question: str) -> Dict:
        """Handle unread email count queries."""
        count = self.storage.get_unread_count()
        answer = f"You have {count} unread emails."

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='aggregation',
            confidence='high',
        )

    def _handle_total_count(self, question: str) -> Dict:
        """Handle total email count queries."""
        count = self.storage.get_total_message_count()
        answer = f"You have {count:,} total emails in your database."

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='aggregation',
            confidence='high',
        )

    def _handle_top_senders(self, question: str) -> Dict:
        """Handle top senders queries."""
        rows = self.storage.get_top_senders(limit=10)

        if rows:
            top_senders = '\n'.join([
                f"{i + 1}. {r['from_addr']}: {r['count']} emails"
                for i, r in enumerate(rows)
            ])
            answer = f"Your top email senders:\n{top_senders}"
        else:
            answer = "I couldn't find sender statistics."

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='aggregation',
            confidence='high',
        )

    def _handle_generic_aggregation(self, question: str) -> Dict:
        """Handle generic aggregation queries."""
        total = self.storage.get_total_message_count()
        answer = f"I found {total:,} emails in your database. Could you be more specific about what statistics you'd like?"

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='aggregation',
            confidence='high',
        )
