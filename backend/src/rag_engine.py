"""RAG (Retrieval-Augmented Generation) engine for email question answering.

This module combines vector search with LLM generation to answer questions
about your emails based on semantic similarity.
"""
from typing import List, Dict, Optional
from .embedding_service import EmbeddingService
from .storage.postgres_storage import PostgresStorage
from .llm_processor import LLMProcessor
import json


class RAGQueryEngine:
    """RAG engine for question-answering over emails.
    
    How it works:
    1. Convert user question to embedding
    2. Find most similar emails using vector search
    3. Build context from retrieved emails
    4. Ask LLM to answer based on context
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
            llm_processor: LLM for generating answers
            top_k: Number of similar emails to retrieve (default: 5)
        """
        self.storage = storage
        self.embedder = embedding_service
        self.llm = llm_processor
        self.top_k = top_k
    
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
        
        # Step 1: Embed the question
        question_embedding = self.embedder.embed_text(question)
        
        # Step 2: Retrieve similar emails
        similar_emails = self.storage.similarity_search(
            query_embedding=question_embedding,
            limit=k,
            threshold=similarity_threshold
        )
        
        if not similar_emails:
            return {
                'answer': "I couldn't find any relevant emails to answer your question.",
                'sources': [],
                'question': question,
                'confidence': 'none'
            }
        
        # Step 3: Build context from retrieved emails
        context = self._build_context(similar_emails)
        
        # Step 4: Generate answer using LLM
        answer = self._generate_answer(question, context)
        
        # Step 5: Format sources
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
        
        return {
            'answer': answer,
            'sources': sources,
            'question': question,
            'confidence': 'high' if similar_emails[0][1] > 0.8 else 'medium' if similar_emails[0][1] > 0.6 else 'low'
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
    
    def _build_context(self, similar_emails: List[tuple]) -> str:
        """Build context string from retrieved emails.
        
        Args:
            similar_emails: List of (MailMessage, similarity_score) tuples
        
        Returns:
            Formatted context string for LLM
        """
        context_parts = []
        
        for idx, (email, score) in enumerate(similar_emails, 1):
            # Format each email for context
            email_context = f"""Email {idx} (Relevance: {score:.2f}):
Subject: {email.subject or 'No subject'}
From: {email.from_ or 'Unknown'}
Date: {email.internal_date or 'Unknown'}
Content: {email.snippet or 'No content available'}
"""
            context_parts.append(email_context)
        
        return "\n".join(context_parts)
    
    def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using LLM with email context.
        
        Args:
            question: User's question
            context: Context built from retrieved emails
        
        Returns:
            LLM-generated answer
        """
        # Build RAG prompt
        prompt = f"""You are an email assistant helping the user find information in their emails.

Based ONLY on the emails provided below, answer the user's question. 

IMPORTANT RULES:
- Only use information from the emails below
- Cite which email(s) you used (by number: Email 1, Email 2, etc.)
- If the emails don't contain enough information, say "I don't have enough information in these emails to answer that question."
- Be concise but informative
- If relevant, mention dates, senders, or other context from the emails

===== RELEVANT EMAILS =====

{context}

===== USER QUESTION =====

{question}

===== YOUR ANSWER =====

Answer the question based on the emails above:"""

        # For RAG, we're not categorizing - we need a text generation approach
        # The LLM processor is designed for classification, so we'll use a simpler approach
        
        # Check if using Ollama (best for RAG)
        if self.llm.provider == "ollama":
            import urllib.request
            import os
            
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
            
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=300) as response:
                result = json.load(response)
                return result.get("response", "Unable to generate answer")
        
        elif self.llm.provider == "openai":
            import openai
            import os
            
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
            return response.choices[0].message.content.strip()
        
        elif self.llm.provider == "anthropic":
            import anthropic
            import os
            
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            message = client.messages.create(
                model=self.llm.model,
                max_tokens=500,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text.strip()
        
        else:
            # Fallback for other providers
            return f"RAG queries require Ollama, OpenAI, or Anthropic. Current provider: {self.llm.provider}"
