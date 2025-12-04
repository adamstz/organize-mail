"""RAG (Retrieval-Augmented Generation) engine for email question answering.

This module provides the main entry point for RAG queries, routing them to
specialized handlers based on query type.
"""
from typing import Dict, List, Optional
import logging

from .embedding_service import EmbeddingService
from ..storage.storage_interface import StorageBackend
from .llm_processor import LLMProcessor
from .context_builder import ContextBuilder
from .query_classifier import QueryClassifier
from .query_handlers import (
    ConversationHandler,
    AggregationHandler,
    SenderHandler,
    AttachmentHandler,
    ClassificationHandler,
    TemporalHandler,
    SemanticHandler,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class RAGQueryEngine:
    """RAG engine for question-answering over emails.

    Routes queries to specialized handlers based on query type:
    - conversation: Greetings, help requests
    - aggregation: Statistics and counting
    - search-by-sender: Find emails from specific sender
    - search-by-attachment: Find emails with attachments
    - classification: Label-based queries
    - temporal: Time-based queries
    - filtered-temporal: Time + content filtered queries
    - semantic: Content-based vector search
    """

    def __init__(
        self,
        storage: StorageBackend,
        embedding_service: EmbeddingService,
        llm_processor: LLMProcessor,
        top_k: int = 5
    ):
        """Initialize RAG engine.

        Args:
            storage: Storage backend with vector search
            embedding_service: Service for generating embeddings
            llm_processor: LangChain-based LLM processor
            top_k: Number of similar emails to retrieve (default: 5)
        """
        self.storage = storage
        self.embedder = embedding_service
        self.llm = llm_processor
        self.top_k = top_k
        self.context_builder = ContextBuilder()

        # Initialize classifier
        self.classifier = QueryClassifier(llm_processor)

        # Initialize handlers
        self.handlers = self._create_handlers()

        logger.info(
            "[RAG INIT] Initialized RAG engine - LLM Provider: %s, Model: %s, Top-K: %s",
            llm_processor.provider,
            llm_processor.model,
            top_k,
        )

    def _create_handlers(self) -> Dict:
        """Create handler instances for each query type."""
        base_args = {
            'storage': self.storage,
            'llm': self.llm,
            'context_builder': self.context_builder,
        }

        return {
            'conversation': ConversationHandler(**base_args),
            'aggregation': AggregationHandler(**base_args),
            'search-by-sender': SenderHandler(**base_args),
            'search-by-attachment': AttachmentHandler(**base_args),
            'classification': ClassificationHandler(**base_args),
            'temporal': TemporalHandler(**base_args),
            'filtered-temporal': TemporalHandler(**base_args),
            'semantic': SemanticHandler(**base_args, embedder=self.embedder),
        }

    def query(
        self,
        question: str,
        top_k: Optional[int] = None,
        similarity_threshold: float = 0.5
    ) -> Dict:
        """Answer a question based on email content.

        Args:
            question: User's question
            top_k: Number of emails to retrieve (uses default if None)
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            Dict with:
                - answer: The LLM's answer
                - sources: List of source emails with metadata
                - question: The original question
                - confidence: 'high', 'medium', 'low', or 'none'
                - query_type: The detected query type
        """
        k = top_k or self.top_k

        logger.info(f"[RAG QUERY] Processing question with {self.llm.provider}/{self.llm.model}")
        logger.info(f"[RAG QUERY] Question: '{question}', top_k: {k}, threshold: {similarity_threshold}")

        # Detect query type
        query_type = self.classifier.detect_query_type(question)
        logger.info(f"[RAG QUERY] Detected query type: {query_type}")

        # Get the appropriate handler
        handler = self.handlers.get(query_type)
        if not handler:
            logger.error(f"[RAG QUERY] No handler for query type: {query_type}")
            return {
                'answer': "I'm not sure how to handle that type of question.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': query_type,
            }

        # Route to handler
        logger.info(f"[RAG QUERY] Routing to {handler.__class__.__name__}")

        # Handle special cases for handlers with extra parameters
        if query_type == 'semantic':
            return handler.handle(question, limit=k, threshold=similarity_threshold)
        elif query_type == 'filtered-temporal':
            return handler.handle_filtered(question, limit=k)
        else:
            return handler.handle(question, limit=k)

    def find_similar_emails(self, message_id: str, limit: int = 5) -> List[Dict]:
        """Find emails similar to a given email.

        Args:
            message_id: ID of the email to find similar emails for
            limit: Number of similar emails to return

        Returns:
            List of similar email metadata with similarity scores
        """
        semantic_handler = self.handlers.get('semantic')
        if semantic_handler and hasattr(semantic_handler, 'find_similar_emails'):
            return semantic_handler.find_similar_emails(message_id, limit)
        return []

    # Legacy method for backwards compatibility
    def _detect_query_type(self, question: str) -> str:
        """Detect query type - delegates to classifier.

        Kept for backwards compatibility.
        """
        return self.classifier.detect_query_type(question)
