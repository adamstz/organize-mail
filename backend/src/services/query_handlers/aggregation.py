"""Handler for aggregation/statistical queries."""
from typing import Dict, Optional
import logging

from .base import QueryHandler
from ..prompt_templates import TOPIC_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class AggregationHandler(QueryHandler):
    """Handle aggregation and statistical queries."""

    def handle(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle an aggregation query.

        Args:
            question: User's question
            limit: Not typically used for aggregation
            chat_history: Optional previous conversation for context

        Returns:
            Query result with statistical answer
        """
        logger.info(f"[AGGREGATION] Processing aggregation query (model: {self.llm.provider}/{self.llm.model})")

        question_lower = question.lower()

        # Check if this is a "how many [topic]" query
        if 'how many' in question_lower and not any(word in question_lower for word in ['total', 'per day', 'unread']):
            result = self._handle_topic_count(question, question_lower, chat_history)
            if result:
                return result
            # Fall through to standard aggregation if topic extraction fails

        # Handle different types of aggregation queries
        # Check for top senders queries first (before generic handling)
        if any(phrase in question_lower for phrase in [
            'who sends', 'who sent', 'whos sent', 'who emails me most',
            'most common sender', 'top sender', 'which sender', 'what sender'
        ]):
            return self._handle_top_senders(question, chat_history)
        elif 'per day' in question_lower or 'daily' in question_lower:
            return self._handle_daily_stats(question, chat_history)
        elif 'how many' in question_lower and ('unread' in question_lower or 'not read' in question_lower):
            return self._handle_unread_count(question, chat_history)
        elif 'how many' in question_lower or 'total' in question_lower:
            return self._handle_total_count(question, chat_history)
        else:
            return self._handle_generic_aggregation(question, chat_history)

    def _handle_topic_count(self, question: str, question_lower: str, chat_history: Optional[list] = None) -> Dict | None:
        """Handle counting emails by topic.

        Returns None if topic extraction fails.
        """
        try:
            topic = self._extract_topic(question, chat_history)
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

    def _extract_topic(self, question: str, chat_history: Optional[list] = None) -> str | None:
        """Extract topic from a counting query using LLM.

        Args:
            question: Current question
            chat_history: Previous conversation for context resolution

        Returns None if extraction fails.
        """
        # Include chat history for context (helps with pronouns and references like "the 97")
        history_context = self._format_chat_history(chat_history) if chat_history else ""

        prompt = TOPIC_EXTRACTION_PROMPT.format(question=question) + history_context
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

    def _handle_daily_stats(self, question: str, chat_history: Optional[list] = None) -> Dict:
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

    def _handle_unread_count(self, question: str, chat_history: Optional[list] = None) -> Dict:
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

    def _handle_total_count(self, question: str, chat_history: Optional[list] = None) -> Dict:
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

    def _handle_top_senders(self, question: str, chat_history: Optional[list] = None) -> Dict:
        """Handle top senders queries.

        Args:
            question: Current question
            chat_history: Previous conversation (may contain topic/filter context)
        """
        # Try to extract a topic filter from question or chat history
        topic = None
        question_lower = question.lower()

        # Check if question references previous context OR is a simple follow-up without specific details
        # Simple questions like "who sends the most?" with no explicit filter should use history context
        has_context_reference = any(phrase in question_lower for phrase in [
            'out of', 'from those', 'of them', 'of the', 'among', 'from the'
        ])

        # If it's a simple question without explicit topic/sender details, try to use history
        is_simple_followup = (
            len(question.split()) <= 5 and  # Short question
            'the most' in question_lower and  # About "most"
            not any(word in question_lower for word in ['all', 'total', 'every'])  # Not asking for everything
        )

        logger.info(f"[AGGREGATION] Top senders query - has_context_reference: {has_context_reference}, "
                    f"is_simple_followup: {is_simple_followup}, has_history: {bool(chat_history)}")

        if (has_context_reference or is_simple_followup) and chat_history:
            logger.info(f"[AGGREGATION] Attempting to extract topic from {len(chat_history)} history messages")
            # Extract topic from chat history
            topic = self._extract_topic_from_history(chat_history)
            if topic:
                logger.info(f"[AGGREGATION] Extracted topic from history: '{topic}'")
            else:
                logger.info("[AGGREGATION] No topic found in chat history")

        # If we have a topic filter, get filtered results
        if topic:
            # Get all emails matching the topic
            emails = self.storage.search_by_keywords([topic], limit=1000)

            # Count senders manually
            sender_counts = {}
            for email in emails:
                sender = email.from_addr or "Unknown"
                sender_counts[sender] = sender_counts.get(sender, 0) + 1

            # Sort by count
            sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            if sorted_senders:
                top_senders = '\n'.join([
                    f"{i + 1}. {sender}: {count} emails"
                    for i, (sender, count) in enumerate(sorted_senders)
                ])
                answer = f"Top senders for '{topic}' emails:\n{top_senders}"
            else:
                answer = f"I couldn't find any emails matching '{topic}'."
        else:
            # No filter, get overall top senders
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

    def _extract_topic_from_history(self, chat_history: list) -> str | None:
        """Extract the most recent topic mentioned in chat history.

        Args:
            chat_history: Previous conversation messages

        Returns:
            Topic string or None
        """
        import re

        logger.debug(f"[AGGREGATION] Searching {len(chat_history)} messages for topic")

        # Look through recent messages for topic mentions
        for i, msg in enumerate(reversed(chat_history[-6:])):  # Last 3 exchanges
            content = msg.get("content", "").lower()
            role = msg.get("role", "")

            logger.debug(f"[AGGREGATION] History [{i}] ({role}): {content[:100]}...")

            # Skip assistant messages that are generic
            if role == "assistant" and "could you be more specific" in content:
                logger.debug(f"[AGGREGATION] Skipping generic assistant message")
                continue

            # Look for promotional/promotion/promo mentions
            if any(word in content for word in ["promotion", "promotional", "promo"]):
                logger.info(f"[AGGREGATION] Found 'promo' keyword in history")
                return "promo"

            # Look for specific topics after "about" or "related to"
            for phrase in ["related to", "about", "regarding", "concerning"]:
                if phrase in content:
                    after_phrase = content.split(phrase, 1)[1].strip()
                    # Extract first meaningful word
                    words = after_phrase.split()
                    if words:
                        topic = words[0].strip("'\".,!?")
                        if len(topic) > 2 and topic not in ['the', 'my', 'your']:
                            return topic

            # Look for "X [topic] emails/messages" patterns (e.g., "198 promo emails")
            match = re.search(r'\d+\s+(\w+)\s+(?:email|message)', content)
            if match:
                potential_topic = match.group(1)
                if potential_topic not in ['total', 'unread', 'new', 'have', 'got']:
                    return potential_topic

            # Look for user questions about topics (e.g., "how many promo mail")
            if role == "user":
                # Extract topic from "how many X" questions
                match = re.search(r'how many\s+(\w+)\s+(?:mail|email|message)', content)
                if match:
                    potential_topic = match.group(1)
                    if potential_topic not in ['total', 'unread', 'new']:
                        return potential_topic

        return None

    def _handle_generic_aggregation(self, question: str, chat_history: Optional[list] = None) -> Dict:
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
