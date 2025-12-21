"""Query classifier for routing queries to appropriate handlers."""
import logging
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from .llm_processor import LLMProcessor
from .prompt_templates import QUERY_CLASSIFICATION_PROMPT
from ..classification_labels import is_classification_query

logger = logging.getLogger(__name__)


class QueryClassifier:
    """Classifies user queries to determine the appropriate handler.

    Uses LLM-based classification with fallback heuristics.
    """

    VALID_TYPES = {
        'conversation', 'aggregation', 'search-by-sender', 'search-by-attachment',
        'classification', 'filtered-temporal', 'temporal', 'semantic'
    }

    def __init__(self, llm: LLMProcessor):
        """Initialize the classifier.

        Args:
            llm: LLM processor for classification
        """
        self.llm = llm

    def detect_query_type(self, question: str, chat_history: Optional[list] = None) -> str:
        """Detect the query type using LLM classification.

        Args:
            question: User's question
            chat_history: Optional list of previous messages for context

        Returns:
            One of: 'conversation', 'aggregation', 'search-by-sender',
                   'search-by-attachment', 'classification', 'filtered-temporal',
                   'temporal', 'semantic'
        """
        # Check if this is a classification query using centralized module first
        if is_classification_query(question):
            return 'classification'

        # Check for contextual follow-up queries that should use classification with context
        if chat_history and self._is_contextual_followup(question, chat_history):
            logger.debug("[QUERY CLASSIFIER] Detected contextual follow-up, routing to classification")
            return 'classification'

        # Use LLM to intelligently classify the query type
        logger.debug("[QUERY CLASSIFIER] Using LLM to classify query type")

        try:
            classification_prompt = QUERY_CLASSIFICATION_PROMPT.replace("{question}", question)
            classification = self._call_llm_simple(classification_prompt).strip().lower()
            detected_type = self._parse_classification(classification)

            logger.debug("[QUERY CLASSIFIER] LLM classified query as: %s", detected_type)
            return detected_type

        except Exception as e:
            logger.debug("[QUERY CLASSIFIER] LLM classification failed (%s), using fallback heuristic", e)
            return self._fallback_classification(question)

    def _call_llm_simple(self, prompt: str) -> str:
        """Call the LLM for classification."""
        if self.llm.llm:
            messages = [
                SystemMessage(content="You are a helpful assistant that provides concise answers."),
                HumanMessage(content=prompt)
            ]
            response = self.llm.llm.invoke(messages)
            return response.content.strip()
        elif self.llm.provider == "rules":
            # Rules provider doesn't have real LLM, force fallback classification
            raise RuntimeError("Rules provider - use fallback classification")
        else:
            return self.llm.invoke(prompt)

    def _parse_classification(self, classification: str) -> str:
        """Parse the LLM classification response.

        Args:
            classification: Raw LLM response

        Returns:
            Normalized query type string
        """
        # Handle common LLM preambles like "the answer is X"
        if 'answer is' in classification:
            parts = classification.split('answer is')
            if len(parts) > 1:
                after_answer = parts[1].strip()
                first_word = after_answer.strip('"\'').split()[0] if after_answer else ''
            else:
                first_word = classification.split()[0] if classification else ''
        else:
            first_word = classification.split()[0] if classification else ''

        # Clean up punctuation
        first_word = first_word.strip('.,!?":;')

        # Normalize underscores to hyphens
        first_word = first_word.replace('_', '-')

        # Check for valid types
        if first_word in self.VALID_TYPES:
            return first_word

        # Map common response words to actual types
        if first_word in ('recent', 'latest', 'newest', 'oldest'):
            return 'filtered-temporal'
        elif first_word == 'count':
            return 'aggregation'
        elif 'conversation' in classification or first_word in ('hello', 'hi', 'thanks', 'help'):
            return 'conversation'
        elif 'aggregation' in classification or 'statistic' in classification or 'count' in first_word:
            return 'aggregation'
        elif 'sender' in classification:
            return 'search-by-sender'
        elif 'attachment' in classification:
            return 'search-by-attachment'
        elif 'filtered-temporal' in classification:
            return 'filtered-temporal'
        elif 'temporal' in classification:
            return 'temporal'
        elif 'semantic' in classification:
            return 'semantic'
        else:
            logger.debug(
                "[QUERY CLASSIFIER] LLM returned unexpected value: '%s', defaulting to semantic",
                classification,
            )
            return 'semantic'

    def _is_contextual_followup(self, question: str, chat_history: list) -> bool:
        """Check if current question is a contextual follow-up that references previous context.

        Args:
            question: Current question
            chat_history: Previous conversation messages

        Returns:
            True if this is a contextual follow-up that should use classification with context
        """
        question_lower = question.lower()

        # Check for contextual reference phrases
        contextual_phrases = [
            'of those', 'from those', 'among them', 'of them', 'out of',
            'from', 'of', 'among', 'from those'
        ]

        has_contextual_reference = any(phrase in question_lower for phrase in contextual_phrases)

        # Check for simple follow-up patterns that don't specify what they're referring to
        # Examples: "who sends most?", "what about senders?", "which ones?"
        is_simple_followup = (
            len(question.split()) <= 6 and  # Short question
            any(phrase in question_lower for phrase in ['who', 'what', 'which', 'how many', 'count']) and
            not any(word in question_lower for word in [
                'all', 'total', 'every', 'overall', 'in general', 'in my'
            ])  # Not asking for everything/general stats
        )

        # Check for numeric references that indicate continuation of previous topic
        has_numeric_reference = any(char.isdigit() for char in question)

        # Look for pronouns that reference previous context
        has_pronouns = any(word in question_lower for word in ['them', 'those', 'they'])

        # Check if we have meaningful chat history to work with
        has_history = bool(chat_history and len(chat_history) >= 2)

        # Enhanced check: Look for very short, ambiguous queries that suggest continuation
        # Examples: "do all 97", "show 97", "list 97"
        is_ambiguous_continuation = (
            len(question.split()) <= 4 and  # Very short
            has_numeric_reference and  # Contains numbers
            not any(word in question_lower for word in ['total', 'overall', 'all', 'every']) and  # Not asking for all emails
            any(phrase in question_lower for phrase in ['do', 'show', 'list', 'get'])  # Action verbs
        )

        # Log for debugging
        logger.debug(
            "[QUERY CLASSIFIER] Contextual analysis - "
            f"has_contextual_reference: {has_contextual_reference}, "
            f"is_simple_followup: {is_simple_followup}, "
            f"has_pronouns: {has_pronouns}, "
            f"has_numeric_reference: {has_numeric_reference}, "
            f"is_ambiguous_continuation: {is_ambiguous_continuation}, "
            f"has_history: {has_history}"
        )

        # This is a contextual follow-up if:
        # 1. It has explicit contextual references, OR
        # 2. It's a simple follow-up with pronouns, OR
        # 3. It's an ambiguous continuation with numbers and we have history
        return (
            has_contextual_reference or
            (is_simple_followup and has_pronouns) or
            (is_ambiguous_continuation and has_history)
        ) and has_history

    def _fallback_classification(self, question: str) -> str:
        """Use heuristics to classify the query when LLM fails.

        Args:
            question: User's question

        Returns:
            Query type string
        """
        question_lower = question.lower()

        # Check for conversational queries
        if any(word in question_lower for word in ['hello', 'hi', 'thanks', 'thank you', 'help', 'what can you']):
            return 'conversation'

        # Check for counting queries
        if 'how many' in question_lower or 'count' in question_lower or 'number of' in question_lower:
            # Check for specific topic
            has_specific_topic = any(word in question_lower for word in [
                'uber', 'amazon', 'linkedin', 'google', 'github', 'facebook',
                'twitter', 'netflix', 'spotify', 'apple', 'microsoft'
            ]) or '@' in question_lower

            if has_specific_topic or 'total' not in question_lower:
                return 'aggregation'

        # Check for temporal patterns
        has_temporal = any(word in question_lower for word in ['recent', 'latest', 'last', 'newest', 'first', 'oldest'])
        has_content_filter = any(word in question_lower for word in ['from', 'about', 'uber', 'amazon', 'linkedin'])

        if has_temporal and has_content_filter:
            return 'filtered-temporal'
        elif has_temporal:
            return 'temporal'
        else:
            return 'semantic'
