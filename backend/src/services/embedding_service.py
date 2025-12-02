"""Embedding service for converting text to vector embeddings.

This module provides local, privacy-preserving text embeddings using sentence-transformers.
No API calls or cloud services are used.
"""
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
import re


class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers.

    Uses the all-MiniLM-L6-v2 model by default (384 dimensions):
    - Fast on CPU (~50-100 emails/second)
    - Good quality for general text
    - Small model size (~80MB)
    - Works completely offline
    """

    # Token limits for the model
    MAX_TOKENS = 400  # Conservative limit for sentence-transformers (actual is ~512)
    CHUNK_OVERLAP_TOKENS = 100  # 25% overlap for chunking

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformers model to use.
                       Default is all-MiniLM-L6-v2 (384 dimensions).
        """
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> List[float]:
        """Convert text to a vector embedding.

        Args:
            text: Text to embed (will be truncated if too long)

        Returns:
            List of floats representing the embedding vector
        """
        print(f"[EMBEDDING SERVICE] Starting text embedding")
        print(f"[EMBEDDING SERVICE] Model: {self.model_name}")
        print(f"[EMBEDDING SERVICE] Input text length: {len(text)} chars")
        print(f"[EMBEDDING SERVICE] Input text preview: {text[:100]}...")

        # Truncate to max tokens to avoid model errors
        original_length = len(text)
        text = self._truncate_text(text, self.MAX_TOKENS)
        if len(text) != original_length:
            print(f"[EMBEDDING SERVICE] Text truncated from {original_length} to {len(text)} chars")

        try:
            # Generate embedding
            print(f"[EMBEDDING SERVICE] Generating embedding with {self.model_name}...")
            embedding = self.model.encode(text, convert_to_numpy=True)

            # Convert to list for JSON serialization
            result = embedding.tolist()
            print(f"[EMBEDDING SERVICE] ✓ Embedding generated successfully")
            print(f"[EMBEDDING SERVICE] Embedding dimensions: {len(result)}")
            return result
        except Exception as e:
            print(f"[EMBEDDING SERVICE] ✗ Embedding generation failed: {e}")
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts in a batch (more efficient than one-by-one).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Truncate all texts
        texts = [self._truncate_text(t, self.MAX_TOKENS) for t in texts]

        # Batch encode for efficiency
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        return [emb.tolist() for emb in embeddings]

    def embed_email(self, subject: str, body: str, from_addr: Optional[str] = None) -> Dict:
        """Embed an email with adaptive chunking strategy.

        For short emails (<400 tokens): Returns single embedding
        For long emails (>=400 tokens): Returns multiple chunk embeddings

        Args:
            subject: Email subject line
            body: Email body text
            from_addr: Sender email address (optional)

        Returns:
            Dict with keys:
                - type: 'single' or 'chunked'
                - embedding: vector (if single)
                - chunks: list of {text, embedding} dicts (if chunked)
                - model: model name used
        """
        # Combine email parts into searchable text
        email_text = self._prepare_email_text(subject, body, from_addr)

        # Count approximate tokens (rough estimate: 1 token ~= 4 chars)
        token_count = self._estimate_tokens(email_text)

        if token_count <= self.MAX_TOKENS:
            # Short email: single embedding
            return {
                'type': 'single',
                'embedding': self.embed_text(email_text),
                'model': self.model_name,
                'token_count': token_count
            }
        else:
            # Long email: chunk with overlap
            chunks = self._chunk_text_with_overlap(email_text)
            chunk_embeddings = self.embed_batch(chunks)

            return {
                'type': 'chunked',
                'chunks': [
                    {'text': text, 'embedding': emb}
                    for text, emb in zip(chunks, chunk_embeddings)
                ],
                'model': self.model_name,
                'token_count': token_count
            }

    def _prepare_email_text(self, subject: str, body: str, from_addr: Optional[str] = None) -> str:
        """Prepare email text for embedding.

        Combines subject, sender, and body in a structured way.
        """
        parts = []

        if subject:
            parts.append(f"Subject: {subject}")

        if from_addr:
            parts.append(f"From: {from_addr}")

        if body:
            # Clean up the body
            body_clean = self._clean_text(body)
            parts.append(body_clean)

        return "\n\n".join(parts)

    def _clean_text(self, text: str) -> str:
        """Clean text by removing excessive whitespace and normalizing."""
        if not text:
            return ""

        # Remove multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove multiple spaces
        text = re.sub(r' {2,}', ' ', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation).

        Better approximation: 1 token ≈ 4 characters for English text
        """
        return len(text) // 4

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to maximum token count."""
        max_chars = max_tokens * 4  # Rough conversion
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _chunk_text_with_overlap(self, text: str) -> List[str]:
        """Split text into overlapping chunks.

        Uses sentence-based chunking with overlap to preserve context.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks with overlap
        """
        # Split into sentences (simple approach)
        sentences = self._split_into_sentences(text)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            # If adding this sentence exceeds limit, save current chunk and start new one
            if current_tokens + sentence_tokens > self.MAX_TOKENS and current_chunk:
                # Save current chunk
                chunks.append(' '.join(current_chunk))

                # Start new chunk with overlap (last few sentences from previous chunk)
                overlap_sentences = self._get_overlap_sentences(
                    current_chunk,
                    self.CHUNK_OVERLAP_TOKENS
                )
                current_chunk = overlap_sentences + [sentence]
                current_tokens = sum(self._estimate_tokens(s) for s in current_chunk)
            else:
                # Add sentence to current chunk
                current_chunk.append(sentence)
                current_tokens += sentence_tokens

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [text]  # Fallback to full text if chunking fails

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences (simple approach).

        Uses regex to split on sentence boundaries.
        """
        # Split on period, question mark, or exclamation followed by space/newline
        sentences = re.split(r'([.!?]+[\s\n]+)', text)

        # Recombine sentence with its punctuation
        result = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
            sentence = sentence.strip()
            if sentence:
                result.append(sentence)

        # If no sentences found, return whole text
        return result if result else [text]

    def _get_overlap_sentences(self, sentences: List[str], overlap_tokens: int) -> List[str]:
        """Get last N sentences that fit within overlap token budget."""
        overlap = []
        token_count = 0

        # Work backwards from end of sentences
        for sentence in reversed(sentences):
            sentence_tokens = self._estimate_tokens(sentence)
            if token_count + sentence_tokens <= overlap_tokens:
                overlap.insert(0, sentence)
                token_count += sentence_tokens
            else:
                break

        return overlap
