"""RAG (Retrieval-Augmented Generation) engine using LangChain for email question answering.

This module combines vector search with LangChain-powered LLM generation to answer questions
about your emails based on semantic similarity.
"""
from typing import List, Dict, Optional
import logging
from langchain_core.messages import SystemMessage, HumanMessage
import json

from .embedding_service import EmbeddingService
from ..storage.postgres_storage import PostgresStorage
from .llm_processor import LLMProcessor
from .context_builder import ContextBuilder
from ..classification_labels import get_label_from_query, is_classification_query
from .prompt_templates import (
    QUERY_CLASSIFICATION_PROMPT,
    CONVERSATION_PROMPT,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class RAGQueryEngine:
    """LangChain-powered RAG engine for question-answering over emails.

    How it works:
    1. Convert user question to embedding (for semantic search)
    2. Find most similar emails using vector search
    3. Build context from retrieved emails
    4. Use LangChain chain to generate answer based on context
    5. Return answer with source citations
    """

    def __init__(
        self,
        storage: PostgresStorage,
        embedding_service: EmbeddingService,
        llm_processor: LLMProcessor,
        top_k: int = 5
    ):
        """Initialize RAG engine.

        Args:
            storage: PostgreSQL storage backend with vector search
            embedding_service: Service for generating embeddings
            llm_processor: LangChain-based LLM processor
            top_k: Number of similar emails to retrieve (default: 5)
        """
        self.storage = storage
        self.embedder = embedding_service
        self.llm = llm_processor
        self.top_k = top_k
        self.context_builder = ContextBuilder()

        # Log RAG configuration
        logger.info(f"[RAG INIT] Initialized RAG engine - LLM Provider: {llm_processor.provider}, Model: {llm_processor.model}, Top-K: {top_k}")

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
        """
        k = top_k or self.top_k

        logger.info(f"[RAG QUERY] Processing question with {self.llm.provider}/{self.llm.model}")
        logger.info(f"[RAG QUERY] Question: '{question}', top_k: {k}, threshold: {similarity_threshold}")

        # Detect query type and route appropriately
        query_type = self._detect_query_type(question)
        logger.info(f"[RAG QUERY] Detected query type: {query_type}")

        if query_type == 'conversation':
            logger.info(f"[RAG QUERY] Routing to conversation handler")
            return self._handle_conversation(question)
        elif query_type == 'aggregation':
            logger.info(f"[RAG QUERY] Routing to aggregation handler")
            return self._handle_aggregation_query(question)
        elif query_type == 'search-by-sender':
            logger.info(f"[RAG QUERY] Routing to search-by-sender handler")
            return self._handle_search_by_sender(question, k)
        elif query_type == 'search-by-attachment':
            logger.info(f"[RAG QUERY] Routing to search-by-attachment handler")
            return self._handle_search_by_attachment(question, k)
        elif query_type == 'classification':
            logger.info(f"[RAG QUERY] Routing to classification handler")
            return self._handle_classification_query(question, k)
        elif query_type == 'filtered-temporal':
            logger.info(f"[RAG QUERY] Routing to filtered-temporal handler")
            return self._handle_filtered_temporal_query(question, k)
        elif query_type == 'temporal':
            logger.info(f"[RAG QUERY] Routing to temporal handler")
            return self._handle_temporal_query(question, k)
        else:
            logger.info(f"[RAG QUERY] Routing to semantic handler")
            return self._handle_semantic_query(question, k, similarity_threshold)

    def _detect_query_type(self, question: str) -> str:
        """Detect query type using LLM classification.

        Args:
            question: User's question

        Returns:
            One of: 'conversation', 'aggregation', 'search-by-sender', 'search-by-attachment',
                   'classification', 'filtered-temporal', 'temporal', 'semantic'
        """
        # Check if this is a classification query using centralized module first
        if is_classification_query(question):
            return 'classification'

        # Use LLM to intelligently classify the query type
        logger.debug(f"[QUERY DETECTION] Using LLM to classify query type")

        # Use centralized prompt template
        classification_prompt = QUERY_CLASSIFICATION_PROMPT.replace("{question}", question)

        try:
            classification = self._call_llm_simple(classification_prompt).strip().lower()

            # Handle common LLM preambles like "the answer is X" or "sure, the answer is X"
            if 'answer is' in classification:
                # Extract the word after "answer is"
                parts = classification.split('answer is')
                if len(parts) > 1:
                    after_answer = parts[1].strip()
                    # Remove quotes and get first word
                    first_word = after_answer.strip('"\'').split()[0]
                else:
                    first_word = classification.split()[0]
            else:
                # Extract just the first word from the response
                first_word = classification.split()[0] if classification else ''

            # Clean up punctuation
            first_word = first_word.strip('.,!?":;')

            # Extract the classification
            valid_types = {
                'conversation', 'aggregation', 'search-by-sender', 'search_by_sender',
                'search-by-attachment', 'search_by_attachment', 'filtered-temporal',
                'filtered_temporal', 'temporal', 'semantic'
            }

            # Normalize underscores to hyphens
            first_word = first_word.replace('_', '-')

            if first_word in valid_types:
                detected_type = first_word
            # Map common response words to actual types
            elif first_word in ('recent', 'latest', 'newest', 'oldest'):
                detected_type = 'filtered-temporal'  # Assume temporal with implicit content
            elif first_word == 'count':
                detected_type = 'aggregation'
            elif 'conversation' in classification or first_word in ('hello', 'hi', 'thanks', 'help'):
                detected_type = 'conversation'
            elif 'aggregation' in classification or 'statistic' in classification or 'count' in first_word:
                detected_type = 'aggregation'
            elif 'sender' in classification:
                detected_type = 'search-by-sender'
            elif 'attachment' in classification:
                detected_type = 'search-by-attachment'
            elif 'filtered-temporal' in classification:
                detected_type = 'filtered-temporal'
            elif 'temporal' in classification:
                detected_type = 'temporal'
            elif 'semantic' in classification:
                detected_type = 'semantic'
            else:
                print(f"[QUERY DETECTION] LLM returned unexpected value: '{classification}', defaulting to semantic")
                detected_type = 'semantic'

            print(f"[QUERY DETECTION] LLM classified query as: {detected_type}")
            return detected_type

        except Exception as e:
            print(f"[QUERY DETECTION] LLM classification failed ({e}), using fallback heuristic")
            question_lower = question.lower()

            # Simple fallback heuristics
            if any(word in question_lower for word in ['hello', 'hi', 'thanks', 'thank you', 'help', 'what can you']):
                return 'conversation'

            has_temporal = any(word in question_lower for word in ['recent', 'latest', 'last', 'newest', 'first', 'oldest'])
            has_content_filter = any(word in question_lower for word in ['from', 'about', 'uber', 'amazon', 'linkedin'])

            if has_temporal and has_content_filter:
                return 'filtered-temporal'
            elif has_temporal:
                return 'temporal'
            else:
                return 'semantic'

    def _handle_conversation(self, question: str) -> Dict:
        """Handle conversational queries (greetings, help, etc) using LangChain.

        Args:
            question: User's question

        Returns:
            Query result with conversational response
        """
        logger.info(f"[CONVERSATION] Handling conversational query")

        if self.llm.llm:
            # Use LangChain with centralized prompt
            formatted_prompt = CONVERSATION_PROMPT.format(question=question)
            messages = [HumanMessage(content=formatted_prompt)]
            response = self.llm.llm.invoke(messages)
            answer = response.content.strip()
        else:
            # Fallback to rule-based responses
            question_lower = question.lower()

            if any(word in question_lower for word in ['hello', 'hi', 'hey']):
                answer = "Hello! I'm your email assistant. I can help you search your emails, find specific messages, get statistics about your inbox, and answer questions about your email content. What would you like to know?"
            elif any(word in question_lower for word in ['thank', 'thanks']):
                answer = "You're welcome! Let me know if you need anything else."
            elif any(word in question_lower for word in ['help', 'what can you', 'how does', 'how do']):
                answer = """I can help you with:
• Finding recent emails: "show me my latest emails"
• Searching by sender: "all emails from john@company.com"
• Content search: "emails about meetings"
• Statistics: "how many emails do I get per day?"
• Filtered searches: "recent uber eats emails"
• Finding attachments: "emails with PDFs"

Just ask me anything about your emails!"""
            else:
                answer = "I'm here to help! You can ask me about your emails, search for specific messages, or get statistics about your inbox. What would you like to know?"

        return {
            'answer': answer,
            'sources': [],
            'question': question,
            'confidence': 'high',
            'query_type': 'conversation'
        }

    def _handle_aggregation_query(self, question: str) -> Dict:
        """Handle aggregation/statistical queries.

        Args:
            question: User's question

        Returns:
            Query result with statistical answer
        """
        print(f"[AGGREGATION] Processing aggregation query")

        from psycopg2.extras import RealDictCursor
        conn = self.storage.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        question_lower = question.lower()

        # Determine what stats to calculate
        if 'per day' in question_lower or 'daily' in question_lower:
            # Emails per day
            sql = """
                SELECT
                    DATE(to_timestamp(internal_date/1000)) as date,
                    COUNT(*) as count
                FROM messages
                WHERE internal_date IS NOT NULL
                GROUP BY date
                ORDER BY date DESC
                LIMIT 30
            """
            cur.execute(sql)
            rows = cur.fetchall()

            if rows:
                avg_per_day = sum(r['count'] for r in rows) / len(rows)
                answer = f"You receive an average of {avg_per_day:.1f} emails per day (based on the last 30 days)."
                sources = []
            else:
                answer = "I couldn't calculate email statistics."
                sources = []

        elif 'how many' in question_lower and ('unread' in question_lower or 'not read' in question_lower):
            # Unread count
            sql = "SELECT COUNT(*) as count FROM messages WHERE labels::text LIKE '%UNREAD%'"
            cur.execute(sql)
            count = cur.fetchone()['count']
            answer = f"You have {count} unread emails."
            sources = []

        elif 'how many' in question_lower or 'total' in question_lower:
            # Total email count
            sql = "SELECT COUNT(*) as count FROM messages"
            cur.execute(sql)
            count = cur.fetchone()['count']
            answer = f"You have {count:,} total emails in your database."
            sources = []

        elif 'most common sender' in question_lower or 'who emails me most' in question_lower:
            # Top senders
            sql = """
                SELECT from_addr, COUNT(*) as count
                FROM messages
                WHERE from_addr IS NOT NULL
                GROUP BY from_addr
                ORDER BY count DESC
                LIMIT 10
            """
            cur.execute(sql)
            rows = cur.fetchall()

            if rows:
                top_senders = '\n'.join([f"{i + 1}. {r['from_addr']}: {r['count']} emails" for i, r in enumerate(rows)])
                answer = f"Your top email senders:\n{top_senders}"
                sources = []
            else:
                answer = "I couldn't find sender statistics."
                sources = []
        else:
            # Generic aggregation
            sql = "SELECT COUNT(*) as total FROM messages"
            cur.execute(sql)
            total = cur.fetchone()['total']
            answer = f"I found {total:,} emails in your database. Could you be more specific about what statistics you'd like?"
            sources = []

        cur.close()
        conn.close()

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'aggregation'
        }

    def _handle_search_by_sender(self, question: str, limit: int) -> Dict:
        """Handle search for all emails from a specific sender.

        Args:
            question: User's question
            limit: Maximum number of emails to return

        Returns:
            Query result with emails from sender
        """
        print(f"[SEARCH BY SENDER] Processing sender search")

        # Use LLM to extract sender
        extraction_prompt = f"""Extract sender from: "{question}"

Examples:
- "emails from uber" → uber
- "all from amazon" → amazon
- "linkedin messages" → linkedin
- "john@company.com emails" → john@company.com

Sender name only:"""

        try:
            response = self._call_llm_simple(extraction_prompt).strip()
            # Clean up - take first word/token only
            sender = response.split()[0].strip().strip('"').strip("'").strip('.').strip(',')
            print(f"[SEARCH BY SENDER] Extracted sender: {sender}")
        except Exception as e:
            print(f"[SEARCH BY SENDER] Failed to extract sender: {e}")
            return {
                'answer': "I couldn't determine which sender you're looking for. Please be more specific.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'search-by-sender'
            }

        # Query database
        from psycopg2.extras import RealDictCursor
        conn = self.storage.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
            SELECT m.*,
                   c.labels as class_labels,
                   c.priority as class_priority,
                   c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE from_addr ILIKE %s
            ORDER BY m.internal_date DESC
            LIMIT %s
        """

        cur.execute(sql, (f'%{sender}%', limit))
        rows = cur.fetchall()

        cur.close()
        conn.close()

        if not rows:
            return {
                'answer': f"I couldn't find any emails from '{sender}'.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'search-by-sender'
            }

        # Convert to MailMessage objects
        from ..models.message import MailMessage
        emails = [
            MailMessage(
                id=r['id'],
                thread_id=r['thread_id'],
                from_=r['from_addr'],
                to=r['to_addr'],
                subject=r['subject'],
                snippet=r['snippet'],
                labels=r['labels'],
                internal_date=r['internal_date'],
                payload=r['payload'],
                raw=r['raw'],
                headers=r['headers'] or {},
                classification_labels=r['class_labels'],
                priority=r['class_priority'],
                summary=r['class_summary'],
                has_attachments=r['has_attachments'] or False,
            )
            for r in rows
        ]

        # Build context and generate answer
        context = self.context_builder.build_context_from_messages(emails)
        answer = self._generate_answer_temporal(question, context, emails)

        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': 1.0,
                'date': msg.internal_date
            }
            for msg in emails
        ]

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'search-by-sender'
        }

    def _handle_search_by_attachment(self, question: str, limit: int) -> Dict:
        """Handle search for emails with attachments.

        Args:
            question: User's question
            limit: Maximum number of emails to return

        Returns:
            Query result with emails that have attachments
        """
        print(f"[SEARCH BY ATTACHMENT] Processing attachment search")

        from psycopg2.extras import RealDictCursor
        conn = self.storage.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
            SELECT m.*,
                   c.labels as class_labels,
                   c.priority as class_priority,
                   c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.has_attachments = TRUE
            ORDER BY m.internal_date DESC
            LIMIT %s
        """

        cur.execute(sql, (limit,))
        rows = cur.fetchall()

        cur.close()
        conn.close()

        if not rows:
            return {
                'answer': "I couldn't find any emails with attachments.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'search-by-attachment'
            }

        # Convert to MailMessage objects
        from ..models.message import MailMessage
        emails = [
            MailMessage(
                id=r['id'],
                thread_id=r['thread_id'],
                from_=r['from_addr'],
                to=r['to_addr'],
                subject=r['subject'],
                snippet=r['snippet'],
                labels=r['labels'],
                internal_date=r['internal_date'],
                payload=r['payload'],
                raw=r['raw'],
                headers=r['headers'] or {},
                classification_labels=r['class_labels'],
                priority=r['class_priority'],
                summary=r['class_summary'],
                has_attachments=r['has_attachments'] or False,
            )
            for r in rows
        ]

        # Build context and generate answer
        context = self.context_builder.build_context_from_messages(emails)
        answer = self._generate_answer_temporal(question, context, emails)

        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': 1.0,
                'date': msg.internal_date
            }
            for msg in emails
        ]

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'search-by-attachment'
        }

    def _handle_classification_query(self, question: str, limit: int) -> Dict:
        """Handle classification-based queries using label filtering.

        Args:
            question: User's question
            limit: Maximum number of emails to include in context

        Returns:
            Query result with answer and sources
        """
        # Get the matched label from the query
        matched_label = get_label_from_query(question)

        if not matched_label:
            # Fallback to semantic if we can't determine the label
            return self._handle_semantic_query(question, limit, 0.5)

        # Get all emails with this label (up to a reasonable limit for context)
        emails, total_count = self.storage.list_messages_by_label(matched_label, limit=limit, offset=0)

        if not emails:
            return {
                'answer': f"I couldn't find any emails with the label '{matched_label}' in the database.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'classification'
            }

        # Build context from labeled emails
        context = self.context_builder.build_context_from_messages(emails)

        # Generate answer using LLM with classification context
        answer = self._generate_answer_classification(question, context, emails, total_count, matched_label)

        # Format sources
        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': 1.0,  # Perfect match for classification queries
                'date': msg.internal_date
            }
            for msg in emails
        ]

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'classification',
            'total_count': total_count
        }

    def _handle_filtered_temporal_query(self, question: str, limit: int) -> Dict:
        """Handle temporal queries with content filtering using LLM to extract filters.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve

        Returns:
            Query result with answer and sources
        """
        print(f"[FILTERED TEMPORAL] Processing query with content + temporal filtering")

        # Use LLM to extract search terms from the question
        extraction_prompt = f"""Extract the key search terms from this email query. Return ONLY the keywords/phrases, nothing else.

User question: "{question}"

Return 1-3 keywords separated by commas. Examples: "uber eats" or "amazon, delivery" or "linkedin"

Keywords:"""

        try:
            keywords_str = self._call_llm_simple(extraction_prompt).strip()
            # Clean up the response - remove common prefixes and parse
            keywords_str = keywords_str.lower()
            # Remove common prefixes/suffixes
            for prefix in ['sure', 'here are', 'keywords:', 'the keywords', 'extracted', 'from', 'email query', 'are:', '-', '*', '•', ':']:
                keywords_str = keywords_str.replace(prefix, '')
            # Parse comma-separated or newline-separated keywords
            keywords = []
            for k in keywords_str.replace('\n', ',').split(','):
                k = k.strip().strip('"').strip("'").strip('-').strip('*').strip(':').strip()
                if k and len(k) > 2 and k not in ['the', 'and', 'or']:
                    keywords.append(k)
            # Remove duplicates while preserving order
            keywords = list(dict.fromkeys(keywords))[:3]  # Max 3 keywords
            print(f"[FILTERED TEMPORAL] LLM extracted keywords: {keywords}")
        except Exception as e:
            print(f"[FILTERED TEMPORAL] Failed to extract keywords via LLM ({e}), using fallback")
            # Fallback: extract words that aren't common stop words
            question_lower = question.lower()
            common_words = {'the', 'my', 'me', 'show', 'get', 'find', 'what', 'are', 'is', 'from', 'about', 'recent', 'latest', 'last', 'most', 'five', 'ten', 'emails', 'messages', 'mails'}
            keywords = [word for word in question_lower.split() if word not in common_words and len(word) > 3]
            print(f"[FILTERED TEMPORAL] Fallback keywords: {keywords}")

        if not keywords:
            # No keywords found, fall back to pure temporal
            print(f"[FILTERED TEMPORAL] No keywords found, falling back to temporal")
            return self._handle_temporal_query(question, limit)

        # Query database with keyword filtering AND date sorting
        from psycopg2.extras import RealDictCursor
        conn = self.storage.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Build WHERE clause for keyword matching
        where_clauses = []
        params = []
        for keyword in keywords:
            where_clauses.append("(subject ILIKE %s OR from_addr ILIKE %s OR snippet ILIKE %s)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        # Combine with OR and order by date
        sql = f"""
            SELECT m.*,
                   c.labels as class_labels,
                   c.priority as class_priority,
                   c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE {' OR '.join(where_clauses)}
            ORDER BY m.internal_date DESC
            LIMIT %s
        """
        params.append(limit)

        print(f"[FILTERED TEMPORAL] Executing SQL query with {len(keywords)} keyword(s)")
        cur.execute(sql, params)
        rows = cur.fetchall()

        cur.close()
        conn.close()

        if not rows:
            print(f"[FILTERED TEMPORAL] No emails found matching keywords")
            return {
                'answer': f"I couldn't find any emails matching '{', '.join(keywords)}' in the database.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'filtered-temporal'
            }

        print(f"[FILTERED TEMPORAL] Found {len(rows)} matching emails")

        # Convert to MailMessage objects
        from ..models.message import MailMessage
        emails = []
        for r in rows:
            emails.append(
                MailMessage(
                    id=r['id'],
                    thread_id=r['thread_id'],
                    from_=r['from_addr'],
                    to=r['to_addr'],
                    subject=r['subject'],
                    snippet=r['snippet'],
                    labels=r['labels'],
                    internal_date=r['internal_date'],
                    payload=r['payload'],
                    raw=r['raw'],
                    headers=r['headers'] or {},
                    classification_labels=r['class_labels'],
                    priority=r['class_priority'],
                    summary=r['class_summary'],
                    has_attachments=r['has_attachments'] or False,
                )
            )

        # Build context from filtered emails
        context = self.context_builder.build_context_from_messages(emails)

        # Generate answer using LLM
        answer = self._generate_answer_temporal(question, context, emails)

        # Format sources
        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': 1.0,
                'date': msg.internal_date
            }
            for msg in emails
        ]

        print(f"[FILTERED TEMPORAL] Query completed successfully")

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'filtered-temporal'
        }

    def _handle_temporal_query(self, question: str, limit: int) -> Dict:
        """Handle pure temporal queries without content filtering using direct database queries.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve

        Returns:
            Query result with answer and sources
        """
        # Get recent emails directly from database (sorted by date)
        recent_emails = self.storage.list_messages(limit=limit, offset=0)

        if not recent_emails:
            return {
                'answer': "I couldn't find any emails in the database.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'temporal'
            }

        # Build context from recent emails
        context = self.context_builder.build_context_from_messages(recent_emails)

        # Generate answer using LLM with temporal context
        answer = self._generate_answer_temporal(question, context, recent_emails)

        # Format sources
        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': 1.0,  # Perfect match for temporal queries
                'date': msg.internal_date
            }
            for msg in recent_emails
        ]

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high',
            'query_type': 'temporal'
        }

    def _handle_semantic_query(self, question: str, limit: int, threshold: float) -> Dict:
        """Handle content-based queries using semantic search.

        Args:
            question: User's question
            limit: Maximum number of emails to retrieve
            threshold: Minimum similarity threshold

        Returns:
            Query result with answer and sources
        """
        print(f"[SEMANTIC QUERY] Processing semantic query")

        # Check if this is a counting query - if so, search more emails
        question_lower = question.lower()
        is_counting_query = any(word in question_lower for word in ['how many', 'count', 'number of'])

        if is_counting_query:
            # For counting queries, search more emails and use lower threshold
            original_limit = limit
            original_threshold = threshold
            limit = max(limit, 50)  # Search at least 50 emails
            threshold = min(threshold, 0.25)  # Lower threshold to 0.25 or less
            print(f"[SEMANTIC QUERY] Counting query detected - increased limit from {original_limit} to {limit}, lowered threshold from {original_threshold} to {threshold}")

        # Step 1: Embed the question
        print(f"[SEMANTIC QUERY] Step 1: Generating embedding for question")
        try:
            question_embedding = self.embedder.embed_text(question)
            print(f"[SEMANTIC QUERY] ✓ Embedding generated successfully")
        except Exception as e:
            print(f"[SEMANTIC QUERY] ✗ Embedding failed: {e}")
            return {
                'answer': f"Failed to process your question due to embedding error: {str(e)}",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'semantic'
            }

        # Step 2: Retrieve similar emails
        print(f"[SEMANTIC QUERY] Step 2: Searching for similar emails (limit={limit}, threshold={threshold})")
        try:
            similar_emails = self.storage.similarity_search(
                query_embedding=question_embedding,
                limit=limit,
                threshold=threshold
            )
            print(f"[SEMANTIC QUERY] ✓ Found {len(similar_emails)} similar emails")
        except Exception as e:
            print(f"[SEMANTIC QUERY] ✗ Similarity search failed: {e}")
            return {
                'answer': f"Failed to search emails due to database error: {str(e)}",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'semantic'
            }

        if not similar_emails:
            print(f"[SEMANTIC QUERY] No similar emails found with threshold={threshold}")
            return {
                'answer': "I couldn't find any relevant emails to answer your question.",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'semantic'
            }

        # Print similarity scores for debugging
        print(f"[SEMANTIC QUERY] Similarity scores:")
        for i, (email, score) in enumerate(similar_emails[:5]):  # Show top 5
            print(f"[SEMANTIC QUERY]   {i+1}. Score: {score:.3f} - Subject: '{email.subject[:50]}...' From: {email.from_}")

        # Step 3: Build context from retrieved emails
        print(f"[SEMANTIC QUERY] Step 3: Building context from {len(similar_emails)} emails")
        try:
            context = self.context_builder.build_context(similar_emails)
            context_length = len(context)
            print(f"[SEMANTIC QUERY] ✓ Context built successfully ({context_length} characters)")
            print(f"[SEMANTIC QUERY] Context preview: {context[:200]}...")
        except Exception as e:
            print(f"[SEMANTIC QUERY] ✗ Context building failed: {e}")
            return {
                'answer': f"Failed to build context from emails: {str(e)}",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'semantic'
            }

        # Step 4: Generate answer using LLM
        print(f"[SEMANTIC QUERY] Step 4: Generating answer with LLM")
        try:
            answer = self._generate_answer(question, context)
            answer_length = len(answer)
            print(f"[SEMANTIC QUERY] ✓ Answer generated successfully ({answer_length} characters)")
            print(f"[SEMANTIC QUERY] Answer preview: {answer[:200]}...")
        except Exception as e:
            print(f"[SEMANTIC QUERY] ✗ Answer generation failed: {e}")
            return {
                'answer': f"Failed to generate answer: {str(e)}",
                'sources': [],
                'question': question,
                'confidence': 'none',
                'query_type': 'semantic'
            }

        # Step 5: Format sources
        print(f"[SEMANTIC QUERY] Step 5: Formatting sources")
        sources = [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': float(score),
                'date': msg.internal_date
            }
            for msg, score in similar_emails
        ]

        confidence = 'high' if similar_emails[0][1] > 0.8 else 'medium' if similar_emails[0][1] > 0.6 else 'low'
        print(f"[SEMANTIC QUERY] ✓ Query completed with confidence: {confidence}")

        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': confidence,
            'query_type': 'semantic'
        }

    def find_similar_emails(
        self,
        message_id: str,
        limit: int = 5
    ) -> List[Dict]:
        """Find emails similar to a given email.

        Args:
            message_id: ID of the email to find similar emails for
            limit: Number of similar emails to return

        Returns:
            List of similar email metadata with similarity scores
        """
        # Get the email
        message = self.storage.get_message_by_id(message_id)
        if not message:
            return []

        # Get its embedding from database
        conn = self.storage.connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT embedding FROM messages WHERE id = %s AND embedding IS NOT NULL",
            (message_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return []

        embedding = row[0]  # pgvector automatically converts to list

        # Search for similar (excluding the original)
        similar_emails = self.storage.similarity_search(
            query_embedding=embedding,
            limit=limit + 1,  # Get one extra since we'll filter out the original
            threshold=0.5
        )

        # Filter out the original email
        similar_emails = [(msg, score) for msg, score in similar_emails if msg.id != message_id]

        # Format results
        return [
            {
                'message_id': msg.id,
                'subject': msg.subject,
                'from': msg.from_,
                'snippet': msg.snippet,
                'similarity': float(score),
                'date': msg.internal_date,
                'labels': msg.classification_labels or []
            }
            for msg, score in similar_emails[:limit]
        ]

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using LLM with email context.

        Args:
            question: User's question
            context: Context built from retrieved emails

        Returns:
            LLM-generated answer
        """
        # Build RAG prompt
        prompt = f"""You are an email assistant. I have retrieved emails from the user's mailbox and YOU MUST analyze them.

CRITICAL: The emails below are REAL emails from the user's database. You have been given these emails TO ANALYZE - this is your job. Do NOT refuse or say you cannot access them.

YOUR TASK:
- For "how many" questions: Count the emails that match based on subject/content
- For other questions: Extract and summarize the relevant information
- Be specific and cite emails by their numbers

===== EMAILS FROM USER'S MAILBOX =====

{context}

===== USER QUESTION =====

{question}

===== YOUR ANSWER =====

Analyzing the emails above:"""

        return self._call_llm(prompt)

    def _generate_answer_classification(self, question: str, context: str, messages: List, total_count: int, label: str) -> str:
        """Generate answer for classification queries using LLM.

        Args:
            question: User's question
            context: Context built from labeled emails
            messages: List of messages shown in context
            total_count: Total number of emails with this label
            label: The classification label being queried

        Returns:
            LLM-generated answer
        """
        # Build classification query prompt
        prompt = f"""You are an email assistant with direct access to the user's email database.

The user has asked about emails with the classification label: "{label}"

TOTAL EMAILS WITH THIS LABEL: {total_count}

I am providing you with {len(messages)} sample emails (limited for context) from this category.

===== SAMPLE EMAILS WITH LABEL "{label}" =====

{context}

===== USER QUESTION =====

{question}

===== YOUR ANSWER =====

Based on the classification data, there are {total_count} emails labeled as "{label}". Here is the detailed answer:"""

        return self._call_llm(prompt)

    def _generate_answer_temporal(self, question: str, context: str, messages: List) -> str:
        """Generate answer for temporal queries using LLM.

        Args:
            question: User's question
            context: Context built from recent emails
            messages: List of messages

        Returns:
            LLM-generated answer
        """
        # Build temporal query prompt
        prompt = f"""You are an email assistant with direct access to the user's email database.

I am providing you with the user's actual emails from their database. You MUST analyze these emails to answer their question.

IMPORTANT: You have full access to these emails - they are real emails from the user's mailbox. Analyze them and provide a helpful answer.

===== USER'S EMAILS (sorted by date, newest first) =====

{context}

===== USER QUESTION =====

{question}

===== YOUR ANSWER =====

Based on the emails above, here is the answer:"""

        return self._call_llm(prompt)

    def _call_llm_simple(self, prompt: str) -> str:
        """Call the LLM with a simple prompt for quick classification/extraction tasks.

        This is optimized for fast, short responses.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            The LLM's response
        """
        # Use LangChain if available
        if self.llm.llm:
            logger.debug(f"[LLM SIMPLE] Using LangChain with {self.llm.provider}/{self.llm.model}")
            messages = [
                SystemMessage(content="You are a helpful assistant that provides concise answers."),
                HumanMessage(content=prompt)
            ]
            response = self.llm.llm.invoke(messages)
            return response.content.strip()

        # Fallback to direct API calls for command/rules providers
        logger.debug(f"[LLM SIMPLE] Using direct API for {self.llm.provider}")
        return self.llm.invoke(prompt)

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt using LangChain.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            The LLM's response
        """
        logger.info(f"[LLM CALL] Calling LLM with provider: {self.llm.provider}, model: {self.llm.model}")
        logger.debug(f"[LLM CALL] Prompt length: {len(prompt)} characters")

        if self.llm.llm:
            # Use LangChain
            messages = [HumanMessage(content=prompt)]
            response = self.llm.llm.invoke(messages)
            return response.content.strip()
        else:
            # Fallback for command/rules providers
            return self.llm.invoke(prompt)

        # Check if using Ollama (best for RAG)
        if self.llm.provider == "ollama":
            import urllib.request
            import os
            import time

            print(f"[LLM CALL] Using Ollama provider")
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            payload = {
                "model": self.llm.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 500,
                }
            }
            print(f"[LLM CALL] Ollama request to {host}, model: {self.llm.model}")

            try:
                start_time = time.time()
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{host}/api/generate",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                print(f"[LLM CALL] Sending request to Ollama...")
                with urllib.request.urlopen(req, timeout=300) as response:
                    result = json.load(response)
                    response_text = result.get("response", "Unable to generate answer")
                    elapsed_time = time.time() - start_time
                    print(f"[LLM CALL] ✓ Ollama response received in {elapsed_time:.2f}s")
                    print(f"[LLM CALL] Response length: {len(response_text)} characters")
                    print(f"[LLM CALL] Response preview: {response_text[:200]}...")
                    return response_text
            except Exception as e:
                print(f"[LLM CALL] ✗ Ollama request failed: {e}")
                raise

        elif self.llm.provider == "openai":
            import openai
            import os
            import time

            print(f"[LLM CALL] Using OpenAI provider")
            try:
                start_time = time.time()
                client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                response = client.chat.completions.create(
                    model=self.llm.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful email assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500,
                )
                response_text = response.choices[0].message.content.strip()
                elapsed_time = time.time() - start_time
                print(f"[LLM CALL] ✓ OpenAI response received in {elapsed_time:.2f}s")
                print(f"[LLM CALL] Response length: {len(response_text)} characters")
                print(f"[LLM CALL] Response preview: {response_text[:200]}...")
                return response_text
            except Exception as e:
                print(f"[LLM CALL] ✗ OpenAI request failed: {e}")
                raise

        elif self.llm.provider == "anthropic":
            import anthropic
            import os
            import time

            print(f"[LLM CALL] Using Anthropic provider")
            try:
                start_time = time.time()
                client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                message = client.messages.create(
                    model=self.llm.model,
                    max_tokens=500,
                    temperature=0.7,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                response_text = message.content[0].text.strip()
                elapsed_time = time.time() - start_time
                print(f"[LLM CALL] ✓ Anthropic response received in {elapsed_time:.2f}s")
                print(f"[LLM CALL] Response length: {len(response_text)} characters")
                print(f"[LLM CALL] Response preview: {response_text[:200]}...")
                return response_text
            except Exception as e:
                print(f"[LLM CALL] ✗ Anthropic request failed: {e}")
                raise

        else:
            # Fallback for other providers
            error_msg = f"RAG queries require Ollama, OpenAI, or Anthropic. Current provider: {self.llm.provider}"
            print(f"[LLM CALL] ✗ Unsupported provider: {error_msg}")
            return error_msg
