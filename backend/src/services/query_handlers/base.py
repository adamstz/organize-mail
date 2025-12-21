"""Base class for query handlers."""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import logging

from ..context_builder import ContextBuilder
from ..llm_processor import LLMProcessor
from ..embedding_service import EmbeddingService
from ...storage.storage_interface import StorageBackend
from ...models.message import MailMessage

logger = logging.getLogger(__name__)


class QueryHandler(ABC):
    """Abstract base class for query handlers.

    Each handler is responsible for processing a specific type of query
    (e.g., conversation, aggregation, semantic search).
    """

    def __init__(
        self,
        storage: StorageBackend,
        llm: LLMProcessor,
        context_builder: ContextBuilder,
        embedder: Optional[EmbeddingService] = None,
    ):
        """Initialize the handler.

        Args:
            storage: Storage backend for database queries
            llm: LLM processor for generating responses
            context_builder: Builder for formatting email context
            embedder: Embedding service (optional, only needed for semantic handler)
        """
        self.storage = storage
        self.llm = llm
        self.context_builder = context_builder
        self.embedder = embedder

    @abstractmethod
    def handle(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle a query and return a response.

        Args:
            question: The user's question
            limit: Maximum number of emails to retrieve/include
            chat_history: Optional list of previous messages for context

        Returns:
            Dict with keys:
                - answer: The generated answer
                - sources: List of source email metadata
                - question: The original question
                - confidence: 'high', 'medium', 'low', or 'none'
                - query_type: The type of query handled
        """
        pass

    def _build_response(
        self,
        answer: str,
        sources: List[Dict],
        question: str,
        query_type: str,
        confidence: str = 'high',
        **extra
    ) -> Dict:
        """Build a standardized response dict.

        Args:
            answer: The generated answer
            sources: List of source metadata dicts
            question: Original question
            query_type: Type of query
            confidence: Confidence level
            **extra: Additional fields to include

        Returns:
            Standardized response dict
        """
        response = {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': confidence,
            'query_type': query_type,
        }
        response.update(extra)
        return response

    def _format_chat_history(self, chat_history: Optional[list] = None) -> str:
        """Format chat history for inclusion in prompts.

        Args:
            chat_history: List of messages [{"role": "user/assistant", "content": "..."}]

        Returns:
            Formatted string representation of chat history
        """
        if not chat_history:
            return ""

        formatted = "\n\nPrevious conversation:\n"
        for msg in chat_history[-6:]:  # Last 3 exchanges (6 messages)
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            formatted += f"{role}: {content}\n"

        return formatted

    def _format_sources(self, emails: List[MailMessage], similarity: float = 1.0) -> List[Dict]:
        """Format a list of emails into source metadata.

        Args:
            emails: List of MailMessage objects
            similarity: Similarity score to assign (default 1.0 for non-semantic)

        Returns:
            List of source metadata dicts
        """
        return [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': similarity,
                'date': msg.internal_date,
            }
            for msg in emails
        ]

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with a prompt.

        Uses LangChain if available, falls back to direct API.

        Args:
            prompt: The prompt to send

        Returns:
            The LLM response text
        """
        from langchain_core.messages import HumanMessage

        logger.debug(f"[{self.__class__.__name__}] Calling LLM, prompt length: {len(prompt)}")

        if self.llm.llm:
            messages = [HumanMessage(content=prompt)]
            response = self.llm.llm.invoke(messages)
            return response.content.strip()
        else:
            return self.llm.invoke(prompt)

    def _call_llm_simple(self, prompt: str) -> str:
        """Call the LLM with a simple prompt for quick extraction/classification.

        Args:
            prompt: The prompt to send

        Returns:
            The LLM response text
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        if self.llm.llm:
            messages = [
                SystemMessage(
                    content="You are a precise extraction assistant. "
                    "Follow instructions exactly. "
                    "Return only the requested information with no explanations or preambles."
                ),
                HumanMessage(content=prompt)
            ]
            response = self.llm.llm.invoke(messages)
            return response.content.strip()
        else:
            return self.llm.invoke(prompt)
