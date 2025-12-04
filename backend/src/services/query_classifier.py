"""Query classifier for routing queries to appropriate handlers."""
from typing import Optional
import logging

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

    def detect_query_type(self, question: str) -> str:
        """Detect the query type using LLM classification.

        Args:
            question: User's question

        Returns:
            One of: 'conversation', 'aggregation', 'search-by-sender',
                   'search-by-attachment', 'classification', 'filtered-temporal',
                   'temporal', 'semantic'
        """
        # Check if this is a classification query using centralized module first
        if is_classification_query(question):
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
