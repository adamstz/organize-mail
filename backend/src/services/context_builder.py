"""Context builder for RAG queries.

This module handles formatting email data into context strings for LLM consumption.
Separates context formatting concerns from the RAG query orchestration.
"""
from typing import List
from datetime import datetime


class ContextBuilder:
    """Builder for creating LLM context from email messages."""

    def build_context(self, similar_emails: List[tuple]) -> str:
        """Build context string from retrieved emails with similarity scores.

        Args:
            similar_emails: List of (MailMessage, similarity_score) tuples

        Returns:
            Formatted context string for LLM
        """
        print(f"[CONTEXT BUILDER] Building context from {len(similar_emails)} similar emails")
        context_parts = []

        for idx, (email, score) in enumerate(similar_emails, 1):
            print(f"[CONTEXT BUILDER] Processing email {idx}: '{email.subject[:50]}...' (score: {score:.3f})")
            email_context = self._format_email_with_score(idx, email, score)
            context_parts.append(email_context)
            print(f"[CONTEXT BUILDER] Email {idx} context length: {len(email_context)} chars")

        final_context = "\n".join(context_parts)
        print(f"[CONTEXT BUILDER] Final context built: {len(final_context)} characters total")
        print(f"[CONTEXT BUILDER] Context preview: {final_context[:300]}...")
        return final_context

    def build_context_from_messages(self, messages: List) -> str:
        """Build context string from messages (without similarity scores).

        Args:
            messages: List of MailMessage objects

        Returns:
            Formatted context string for LLM
        """
        context_parts = []

        for idx, email in enumerate(messages, 1):
            email_context = self._format_email(idx, email)
            context_parts.append(email_context)

        return "\n".join(context_parts)

    def _format_email_with_score(self, idx: int, email, score: float) -> str:
        """Format a single email with similarity score for context.

        Args:
            idx: Email index number
            email: MailMessage object
            score: Similarity score

        Returns:
            Formatted email string
        """
        date_str = self._format_date(email.internal_date)

        return f"""Email {idx} (Relevance: {score:.2f}):
Subject: {email.subject or 'No subject'}
From: {email.from_ or 'Unknown'}
Date: {date_str}
Content: {email.snippet or 'No content available'}
"""

    def _format_email(self, idx: int, email) -> str:
        """Format a single email without similarity score for context.

        Args:
            idx: Email index number
            email: MailMessage object

        Returns:
            Formatted email string
        """
        date_str = self._format_date(email.internal_date)

        return f"""Email {idx}:
Subject: {email.subject or 'No subject'}
From: {email.from_ or 'Unknown'}
Date: {date_str}
Content: {email.snippet or 'No content available'}
"""

    def _format_date(self, internal_date) -> str:
        """Format email date from milliseconds timestamp.

        Args:
            internal_date: Milliseconds since epoch or None

        Returns:
            Formatted date string
        """
        try:
            if internal_date:
                # internal_date is milliseconds since epoch
                dt = datetime.fromtimestamp(internal_date / 1000)
                return dt.strftime('%Y-%m-%d %H:%M')
            else:
                return 'Unknown'
        except Exception:
            return str(internal_date or 'Unknown')
