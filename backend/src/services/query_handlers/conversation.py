"""Handler for conversational queries (greetings, help, etc)."""
from typing import Dict, Optional
import logging

from langchain_core.messages import HumanMessage

from .base import QueryHandler
from ..prompt_templates import CONVERSATION_PROMPT

logger = logging.getLogger(__name__)


class ConversationHandler(QueryHandler):
    """Handle conversational queries like greetings and help requests."""

    def handle(self, question: str, limit: int = 5, chat_history: Optional[list] = None) -> Dict:
        """Handle a conversational query.

        Args:
            question: User's question
            limit: Not used for conversation

        Returns:
            Query result with conversational response
        """
        logger.info(f"[CONVERSATION] Handling conversational query (model: {self.llm.provider}/{self.llm.model})")

        if self.llm.llm:
            # Use LangChain with centralized prompt
            formatted_prompt = CONVERSATION_PROMPT.format(question=question)
            messages = [HumanMessage(content=formatted_prompt)]
            response = self.llm.llm.invoke(messages)
            answer = response.content.strip()
        else:
            # Fallback to rule-based responses
            answer = self._get_fallback_response(question)

        return self._build_response(
            answer=answer,
            sources=[],
            question=question,
            query_type='conversation',
            confidence='high',
        )

    def _get_fallback_response(self, question: str) -> str:
        """Generate a rule-based fallback response.

        Args:
            question: User's question

        Returns:
            Appropriate response string
        """
        question_lower = question.lower()

        if any(word in question_lower for word in ['hello', 'hi', 'hey']):
            return (
                "Hello! I'm your email assistant. I can help you search your emails, "
                "find specific messages, get statistics about your inbox, and answer "
                "questions about your email content. What would you like to know?"
            )
        elif any(word in question_lower for word in ['thank', 'thanks']):
            return "You're welcome! Let me know if you need anything else."
        elif any(word in question_lower for word in ['help', 'what can you', 'how does', 'how do']):
            return """I can help you with:
• Finding recent emails: "show me my latest emails"
• Searching by sender: "all emails from john@company.com"
• Content search: "emails about meetings"
• Statistics: "how many emails do I get per day?"
• Filtered searches: "recent uber eats emails"
• Finding attachments: "emails with PDFs"

Just ask me anything about your emails!"""
        else:
            return (
                "I'm here to help! You can ask me about your emails, search for "
                "specific messages, or get statistics about your inbox. What would "
                "you like to know?"
            )
