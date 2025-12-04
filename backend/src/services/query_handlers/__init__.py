"""Query handlers package for RAG engine.

This package contains specialized handlers for different query types,
each implementing the QueryHandler interface.
"""

from .base import QueryHandler
from .conversation import ConversationHandler
from .aggregation import AggregationHandler
from .sender import SenderHandler
from .attachment import AttachmentHandler
from .classification import ClassificationHandler
from .temporal import TemporalHandler
from .semantic import SemanticHandler

__all__ = [
    'QueryHandler',
    'ConversationHandler',
    'AggregationHandler',
    'SenderHandler',
    'AttachmentHandler',
    'ClassificationHandler',
    'TemporalHandler',
    'SemanticHandler',
]
