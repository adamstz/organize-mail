# Query Flow and LLM Processing Pipeline

This document describes the complete flow of user queries through the mail-organizer system, including all LLM interactions, classification logic, retrieval strategies, and handler routing.

## Table of Contents
1. [Overview](#overview)
2. [Query Flow Diagram](#query-flow-diagram)
3. [Classification System](#classification-system)
4. [Retrieval Pipeline (Hybrid Search)](#retrieval-pipeline-hybrid-search)
5. [Handler Routing and Execution](#handler-routing-and-execution)
6. [Number Extraction for Limits](#number-extraction-for-limits)
7. [LLM Interactions](#llm-interactions)
8. [Testing and Validation](#testing-and-validation)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The mail-organizer uses a multi-stage pipeline to process user questions about their emails:

```
User Query → API → RAG Engine → Classifier → Handler → LLM → Response
                                      ↓
                                Storage (Postgres + pgvector)
                                      ↓
                           Hybrid Search + Reranking
```

**Key Components:**
- **API Layer**: FastAPI endpoint receiving queries
- **RAG Engine**: Orchestrates the query processing pipeline
- **Query Classifier**: Determines intent and routes to appropriate handler
- **8 Specialized Handlers**: Execute different query types
- **Hybrid Search**: Vector + keyword search with cross-encoder reranking
- **LLM Processor**: Abstracts multiple LLM providers (OpenAI, Anthropic, Ollama, etc.)

---

## Query Flow Diagram

### Complete Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API Request                                                  │
│    POST /api/query                                              │
│    {"question": "what are my last 10 ubereats mail",           │
│     "top_k": 5, "chat_session_id": "abc123"}                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Chat History Retrieval (if chat_session_id provided)        │
│    - Fetch previous messages from chat session                  │
│    - Format as [{"role": "user/assistant", "content": "..."}]  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. RAG Engine.query()                                          │
│    Parameters: question, top_k, similarity_threshold,           │
│                chat_history                                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Query Classification (LLM Call #1)                          │
│    - QueryClassifier.detect_query_type()                        │
│    - LLM receives QUERY_CLASSIFICATION_PROMPT                   │
│    - Returns one of 8 types: conversation, aggregation,         │
│      search-by-sender, search-by-attachment, classification,    │
│      filtered-temporal, temporal, semantic                      │
│    - Intent-based: "What does user want to DO?"                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Number Extraction (for search-by-sender)                    │
│    - Extract "10" from "last 10 ubereats mail"                 │
│    - Override default top_k with extracted number              │
│    - Patterns: "last N", "show N", "N emails"                  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Handler Selection & Routing                                 │
│    - RAG Engine routes to appropriate handler                  │
│    - Passes: question, limit, chat_history                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┬────────────┬────────────┐
        ▼                         ▼            ▼            ▼
   ┌─────────┐            ┌──────────────┐  [Other      [Other
   │ Sender  │            │   Semantic   │  handlers]   handlers]
   │ Handler │            │   Handler    │
   └────┬────┘            └──────┬───────┘
        │                        │
        ▼                        ▼
   ┌─────────────────────┐  ┌──────────────────────────────┐
   │ 7a. Sender Extract  │  │ 7b. Hybrid Search            │
   │     (LLM Call #2)   │  │     - Vector search (50)     │
   │  Extract "ubereats" │  │     - Keyword search (50)    │
   │  from query         │  │     - RRF fusion             │
   └────┬────────────────┘  │     - Cross-encoder rerank   │
        │                   │     - Return top 5           │
        ▼                   └──────┬───────────────────────┘
   ┌─────────────────────┐        │
   │ 8a. DB Query        │        │
   │  search_by_sender() │        │
   │  (10 emails)        │◄───────┘
   └────┬────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Context Building                                             │
│    - Format emails with full body text (up to 2000 chars)      │
│    - Include chat_history for pronoun resolution                │
│    - Build prompt for LLM                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 10. Answer Generation (LLM Call #3)                            │
│     - LLM receives handler-specific prompt                      │
│     - Prompt includes: question, email context, chat history    │
│     - Returns natural language answer                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 11. Response Formatting                                         │
│     {                                                           │
│       "answer": "Based on the emails...",                       │
│       "sources": [{"message_id": "...", "subject": "..."}],    │
│       "query_type": "search-by-sender",                        │
│       "confidence": "high"                                      │
│     }                                                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 12. Save to Chat Session (if chat_session_id provided)         │
│     - Save assistant response to database                       │
│     - Used for future contextual queries                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
                 Return to User
```

**LLM Calls Summary for "what are my last 10 ubereats mail":**
1. **Classification**: Determines query type → `search-by-sender`
2. **Sender Extraction**: Extracts sender name → `ubereats`
3. **Answer Generation**: Creates natural language response from email context

Total: **3 LLM calls per query** (typical for search-by-sender)

---

## Classification System

### Intent-Based Classification

The system classifies queries by **intent** (what user wants to DO), not by context-dependency.

**File**: `backend/src/services/prompt_templates.py` (QUERY_CLASSIFICATION_PROMPT)

#### Key Design Principles

**Before (Problematic):**
```
Classifier: Is this a "contextual follow-up"?
  → Special routing to classification handler
  → Handler tries to extract context
```
**Problem**: Confuses context-dependency with intent

**After (Intent-Based) ✅:**
```
Classifier: What does the user want to DO?
  → "filter by label" → classification
  → "count something" → aggregation
  → "get from sender" → search-by-sender

Handler: Receives chat_history, resolves pronouns naturally
  → "those" = previous results from chat_history
  → Handler knows how to use context for its specific intent
```

### 8 Query Types

| Type | Intent | Examples |
|------|--------|----------|
| **conversation** | Chat/greeting | "hello", "thanks", "help me" |
| **aggregation** | Count/summarize | "how many emails", "total messages" |
| **search-by-sender** | Filter by sender | "last 10 ubereats mail", "amazon emails" |
| **search-by-attachment** | Has attachments | "emails with PDFs", "find attachments" |
| **classification** | Filter by label | "show spam", "which are receipts" |
| **filtered-temporal** | Time + sender | "uber emails last month" |
| **temporal** | Time-based only | "emails from yesterday" |
| **semantic** | Content search | "about invoices", "meeting notes" |

### Prompt Structure (Simplified for Small LLMs)

**Evolution:**
- **Before**: 100+ lines with complex priority rules, nested conditions, verbose explanations
- **After**: 65 lines with simple format: type + examples

**Example from prompt:**
```
Classify this email query by INTENT (what user wants to DO).

Pronouns reference previous context - focus on what user wants to DO.

Types and examples:

search-by-sender (emails from a company/person):
- "last 10 ubereats mail"           ← First example (exact match!)
- "show me amazon emails"
- "emails from uber"
- "doordash notifications"
- "linkedin messages"
- "github emails"
- "show me slack messages"
- "what did spotify send me"

classification (filter by label/category):
- "show me spam"
- "which are receipts"
- "of those, which are spam"        ← Intent doesn't change with pronouns
- "from them, show receipts"

aggregation (count/summarize):
- "how many emails"
- "total messages"
- "of those, how many"              ← Same intent: count

KEY RULE: Company/brand names (uber, ubereats, amazon, linkedin...) 
          always classify as search-by-sender

Classification:
```

### Contextual Queries (Pronouns)

**Architecture Benefit**: No special "contextual follow-up" type needed

```python
# User: "show me job applications"
# → classification handler gets job-application emails

# User: "of those, which are interviews?"  
# → classification handler receives chat_history
# → handler's prompt includes previous Q&A
# → LLM sees: "Previous: User asked about job applications"
# → Understands "those" = job applications
# → Filters for interview label
```

**All handlers** have `_format_chat_history()` method:
```python
def _format_chat_history(chat_history):
    """Format last 3 exchanges (6 messages) for LLM context."""
    formatted = "\n\nPrevious conversation:\n"
    for msg in chat_history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted += f"{role}: {msg['content']}\n"
    return formatted
```

### Classification Process

**File**: `backend/src/services/query_classifier.py`

```python
def detect_query_type(question: str, chat_history: Optional[list] = None) -> str:
    # 1. Format prompt with question
    prompt = QUERY_CLASSIFICATION_PROMPT.format(question=question)
    
    # 2. Add chat history if provided (helps LLM understand context)
    if chat_history:
        history_text = format_chat_history(chat_history)
        prompt += f"\n\nPrevious conversation:\n{history_text}"
    
    # 3. Call LLM
    response = llm.invoke(prompt)
    
    # 4. Parse response (handles various formats)
    # Removes prefixes like "the answer is", "classification:", etc.
    # Searches entire response for valid type names
    query_type = parse_classification(response)
    
    # 5. Return validated type (must be one of 8 valid types)
    return query_type
```

**Debug Logging:**
```
[QUERY CLASSIFIER] Question: 'what are my last 10 ubereats mail'
[QUERY CLASSIFIER] Calling LLM for classification
[QUERY CLASSIFIER] Raw LLM response: 'search-by-sender'
[QUERY CLASSIFIER] Detected type: search-by-sender
```

**Performance:**
- Before (complex prompt): 82 seconds with olmo2:7b
- After (simplified prompt): 5-15 seconds with olmo2:7b

---

## Retrieval Pipeline (Hybrid Search)

### Industry-Standard RAG Improvements

The system uses a three-stage retrieval pipeline for semantic queries:

```
Query → Hybrid Search → Cross-Encoder Reranking → LLM Answer Generation
         (100 candidates)    (top 5 most relevant)
```

### 1. Hybrid Search (Vector + Keyword)

**File**: `backend/src/storage/postgres_storage.py`

**Combines two retrieval methods:**

#### Vector Search (Semantic)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Query → embedding → pgvector similarity search
- Retrieves: 50 candidates

#### Keyword Search (Lexical)
- PostgreSQL full-text search (tsvector)
- Weighted fields:
  - Subject: weight 'A' (highest)
  - Snippet: weight 'B'
  - Sender: weight 'C'
- Retrieves: 50 candidates

#### Reciprocal Rank Fusion (RRF)

Merges ranked results from both methods using industry-standard algorithm:

```python
def rrf_score(rank, weight, k=60):
    """
    Industry-standard RRF formula.
    k=60 is standard constant (Cormack et al., SIGIR 2009)
    """
    return weight / (k + rank)

# For each result:
vector_score = 0.6 / (60 + vector_rank)   # 60% weight
keyword_score = 0.4 / (60 + keyword_rank)  # 40% weight
final_score = vector_score + keyword_score

# Sort by final_score, return top 50 for reranking
```

**Default Configuration:**
- Vector weight: 0.6 (60%) - semantic matching
- Keyword weight: 0.4 (40%) - exact matching
- Retrieval K: 50 candidates per method
- RRF constant: k=60 (industry standard)

### 2. Cross-Encoder Reranking

**File**: `backend/src/services/query_handlers/semantic.py`

**Why needed?**
- Bi-encoders (embedding models) are fast but less accurate
- Cross-encoders directly compare query + document pairs
- Much more accurate relevance scoring

**Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2`

**Process:**
```python
# 1. Retrieve broad set (50 candidates from hybrid search)
candidates = storage.hybrid_search(query, embedding, retrieval_k=50)

# 2. Rerank with cross-encoder
pairs = [(query, email.get_body_text()) for email in candidates]
scores = cross_encoder.predict(pairs)

# 3. Return top 5 most relevant
sorted_results = sorted(zip(candidates, scores), 
                       key=lambda x: x[1], 
                       reverse=True)[:5]
```

**Performance:**
- Lazy loading: Model loaded on first use, cached
- Prediction time: ~100-500ms for 50 pairs
- Memory: ~100MB for model

### 3. Full Email Body Context

**Files**: 
- `backend/src/models/message.py` (body extraction)
- `backend/src/services/context_builder.py` (formatting)

**Before:**
- Only used 160-char snippet
- LLM had incomplete information
- Answers were vague or incorrect

**After:**
- Extracts full email body (up to 2000 chars)
- Recursively parses Gmail API payload
- Prefers text/plain over text/html
- Falls back to snippet if no body available

**Body Extraction Logic:**
```python
def get_body_text(message) -> str:
    """
    Extract full text from Gmail payload.
    Handles: simple text, multipart, nested multipart
    """
    # 1. Check for simple text/plain body
    if payload.mimeType == 'text/plain':
        return base64_decode(payload.body.data)
    
    # 2. Handle multipart (prefer text/plain)
    if payload.parts:
        for part in payload.parts:
            if part.mimeType == 'text/plain':
                return base64_decode(part.body.data)
        # Fallback to HTML if no plain text
        for part in payload.parts:
            if part.mimeType == 'text/html':
                return strip_html(base64_decode(part.body.data))
    
    # 3. Recurse for nested multipart
    # 4. Fallback to snippet
    return message.snippet
```

### Database Migration

**File**: `backend/src/storage/migrations/001_add_fulltext_search.sql`

**Setup (one-time):**
```bash
cd backend
python run_migration.py src/storage/migrations/001_add_fulltext_search.sql
```

**What it does:**
1. Adds `search_vector` tsvector column
2. Creates GIN index for fast keyword search
3. Adds trigger to auto-update on INSERT/UPDATE
4. Backfills existing messages

**Verification:**
```sql
-- Check column exists
SELECT search_vector FROM messages LIMIT 1;

-- Check index
SELECT indexname FROM pg_indexes 
WHERE tablename = 'messages' 
  AND indexname = 'idx_messages_search_vector';
```

### Retrieval Quality Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Recall** | Vector-only, misses exact matches | Hybrid catches both semantic + exact |
| **Precision** | Bi-encoder only | Cross-encoder reranking |
| **Context** | 160-char snippet | 2000-char full body |
| **Answer Quality** | Vague, incomplete | Accurate, detailed |

---

## Handler Routing and Execution

### Handler Selection

**File**: `backend/src/services/rag_engine.py`

```python
# Map query types to handlers
handlers = {
    'conversation': ConversationHandler,
    'aggregation': AggregationHandler,
    'search-by-sender': SenderHandler,
    'search-by-attachment': AttachmentHandler,
    'classification': ClassificationHandler,
    'filtered-temporal': FilteredTemporalHandler,
    'temporal': TemporalHandler,
    'semantic': SemanticHandler,
}

# Route based on classification
handler = handlers[query_type]
result = handler.handle(
    question=question,
    limit=top_k,
    chat_history=chat_history
)
```

### Handler Responsibilities

Each handler follows the same pattern:

```python
class SomeHandler(QueryHandler):
    def handle(self, question: str, limit: int = 5, 
               chat_history: Optional[list] = None) -> Dict:
        # 1. Extract parameters (if needed, may use LLM)
        # 2. Query database
        # 3. Build context from results
        # 4. Generate answer using LLM
        # 5. Format response
        return {
            'answer': "...",
            'sources': [...],
            'query_type': "...",
            'confidence': "high|medium|low|none"
        }
```

### Example: SenderHandler Flow

**File**: `backend/src/services/query_handlers/sender.py`

```python
def handle(question, limit, chat_history):
    # 1. Extract number from query (NEW!)
    requested_limit = extract_number_from_query(question)
    if requested_limit:
        limit = requested_limit  # "last 10" → limit=10
    
    # 2. Extract sender (LLM call)
    sender = extract_sender(question, chat_history)
    # "what are my last 10 ubereats mail" → "ubereats"
    
    # 3. Query database
    emails = storage.search_by_sender(sender, limit=limit)
    # Returns 10 MailMessage objects
    
    # 4. Build context (full email bodies)
    context = context_builder.build_context_from_messages(emails)
    
    # 5. Generate answer (LLM call)
    answer = generate_answer(question, context, sender, chat_history)
    
    # 6. Format response
    return {
        'answer': answer,
        'sources': format_sources(emails),  # All 10 sources
        'query_type': 'search-by-sender',
        'confidence': 'high'
    }
```

### Clearer Separation of Concerns

**Classifier's job**: What is the user trying to DO?
- Count things? → aggregation
- Filter by label? → classification  
- Get from sender? → search-by-sender
- Search content? → semantic

**Handler's job**: Execute the intent using available context
- Use chat_history to resolve pronouns
- Apply the intent to appropriate emails
- Generate natural response

---

## Number Extraction for Limits

### Problem

User says "last 10 ubereats mail" but default `top_k=5`:
- Only 5 emails retrieved from database
- LLM tries to list 10 items but only has 5
- Answer cuts off mid-sentence (stops at item 8)

### Solution

**File**: `backend/src/services/query_handlers/sender.py`

Extract numbers from queries and override default limit:

```python
def _extract_number_from_query(question: str) -> Optional[int]:
    """Extract N from 'last N emails', 'show N messages', etc."""
    patterns = [
        r'\b(?:last|recent|latest)\s+(\d+)\b',      # "last 10"
        r'\b(?:show|get|find)\s+(?:me\s+)?(\d+)\b', # "show me 20"
        r'\b(\d+)\s+(?:emails?|messages?|mails?)\b', # "10 emails"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            # Sanity check: 1-100 range
            if 1 <= num <= 100:
                return num
    
    return None
```

**Usage in handler:**
```python
def handle(question, limit=5, chat_history=None):
    # Override limit if number in query
    requested_limit = extract_number_from_query(question)
    if requested_limit:
        limit = requested_limit
        logger.info(f"Extracted limit from query: {limit}")
    
    # Now retrieve correct number of emails
    emails = storage.search_by_sender(sender, limit=limit)
```

**Examples:**
- "last 10 ubereats mail" → limit=10
- "show me 20 amazon emails" → limit=20
- "get 5 messages from linkedin" → limit=5
- "uber emails" → limit=5 (default)

**Benefits:**
- ✅ All 10 sources in response (not just 5)
- ✅ LLM has enough emails to list all requested items
- ✅ Answer doesn't cut off mid-sentence

---

## LLM Interactions

### LLM Provider Architecture

**File**: `backend/src/services/llm_processor.py`

**Supports multiple providers:**
- OpenAI (GPT-4, GPT-3.5, etc.)
- Anthropic (Claude)
- Ollama (local models like llama3, olmo2:7b)
- External command (custom LLM)
- Rules (keyword-based fallback for tests)

**Auto-detection:**
```python
# Detects provider based on environment variables
if os.getenv('OPENAI_API_KEY'):
    provider = 'openai'
elif os.getenv('ANTHROPIC_API_KEY'):
    provider = 'anthropic'
elif os.getenv('OLLAMA_HOST'):
    provider = 'ollama'
# etc.
```

### LLM Call Points

**3 main LLM interactions per typical query:**

#### 1. Classification (QueryClassifier)
```python
# Prompt: QUERY_CLASSIFICATION_PROMPT
# Input: User question + chat history
# Output: One of 8 query types
# Temp: 0.3 (low, want consistent classification)
# Max tokens: 200

prompt = """
Classify this email query by INTENT (what user wants to DO).

Types and examples:
[8 types with 8-10 examples each]

Query: "what are my last 10 ubereats mail"

Classification:
"""

response = llm.invoke(prompt)  # → "search-by-sender"
```

#### 2. Parameter Extraction (Handler-specific)

**Example: Sender extraction**
```python
# Prompt: SENDER_EXTRACTION_PROMPT  
# Input: Question + chat history
# Output: Sender name/email
# Temp: 0.3
# Max tokens: 50

prompt = """
Extract the sender/company name from this query.
Return ONLY the sender name, nothing else.

Query: "what are my last 10 ubereats mail"

Sender:
"""

response = llm.invoke(prompt)  # → "ubereats"
```

#### 3. Answer Generation (All handlers)

```python
# Prompt: Handler-specific (SEARCH_BY_SENDER_PROMPT, etc.)
# Input: Question + email context + chat history
# Output: Natural language answer
# Temp: 0.7 (higher for creative answers)
# Max tokens: 500

prompt = """
You are an email assistant. The emails below are from: ubereats

YOUR TASK: Answer the question about emails from this sender.
- Summarize email content
- Note patterns or themes
- Count if asked
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== EMAILS FROM ubereats =====

Email 1:
Subject: BOGO SONIC® Cheeseburger
From: uber.us@uber.com
Date: 2024-12-20
Body: Members, get BOGO SONIC® Cheeseburger with $0 Delivery Fee...
[Up to 2000 chars per email]

[... 10 emails total ...]

===== USER QUESTION =====

what are my last 10 ubereats mail

Previous conversation:
[Chat history if available]

Answer naturally based on the emails above.
"""

response = llm.invoke(prompt)
```

### LLM Configuration

**Default Settings** (in LLMProcessor):
- Temperature: 0.3 (classification), 0.7 (answers)
- Max tokens: 200 (classification), 500 (answers)
- Timeout: 60 seconds (increased for slow local models)

**Environment Variables:**
```bash
# Provider selection
export LLM_PROVIDER=ollama  # or openai, anthropic, command, rules
export OLLAMA_HOST=http://localhost:11434
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=...

# Model override
export LLM_MODEL=olmo2:7b  # or gpt-4, claude-3-haiku, llama3, etc.
```

### Debug Logging

**Full LLM trace:**
```
[LLM PROCESSOR] Provider: ollama, Model: olmo2:7b
[LLM PROCESSOR] Prompt (500 chars):
Classify this email query by INTENT...

[LLM PROCESSOR] Response (15 chars):
search-by-sender

[LLM PROCESSOR] Invocation completed in 12.3s
```

---

## Testing and Validation

### Test Coverage

**Unit Tests:**
- `tests/unit/test_query_classifier.py` - Classification logic
  - UberEats query tests
  - Company name variations
  - Intent-based classification
  - Contextual queries
- `tests/unit/test_query_handlers.py` - Handler logic
  - Number extraction tests
  - Limit handling tests
  - All 8 handlers
- `tests/unit/test_hybrid_search.py` - Retrieval pipeline
  - RRF fusion
  - Cross-encoder reranking
  - Full body extraction
- `tests/unit/test_keyword_search.py` - Keyword search logic

**Integration Tests:**
- `tests/integration/test_chat_history_flow.py` - Contextual queries
- `tests/integration/test_migration_001.py` - Database migration
- `tests/integration/test_search_performance.py` - Query performance

**Total**: 293+ passing tests

### Running Tests

```bash
cd backend

# All unit tests
make test-unit

# Classification tests only
pytest tests/unit/test_query_classifier.py -v

# Handler tests
pytest tests/unit/test_query_handlers.py::TestSenderHandler -v

# Hybrid search tests
pytest tests/unit/test_hybrid_search.py -v

# Integration tests
pytest tests/integration/ -v

# Full suite
make test
```

### Expected Test Results

**Contextual queries classify by intent:**

| Query | Intent | Type |
|-------|--------|------|
| "of those, which are spam" | filter by label | classification |
| "from them, show receipts" | filter by label | classification |
| "of those, how many" | count | aggregation |
| "which are interviews" | filter by label | classification |

---

## Troubleshooting

### Classification Issues

**Problem**: Query classified incorrectly

**Debug steps:**
1. Check classification logs:
   ```bash
   # Look for [QUERY CLASSIFIER] lines
   tail -f logs/backend.log | grep CLASSIFIER
   ```

2. Review raw LLM response:
   ```
   [QUERY CLASSIFIER] Raw LLM response: 'semantic'
   [QUERY CLASSIFIER] Detected type: semantic
   ```

3. Check if prompt needs more examples:
   - Edit `backend/src/services/prompt_templates.py`
   - Add failing query as example under correct type
   - Restart server

4. Try stronger LLM for classification:
   ```bash
   # Use GPT-4 just for classification
   export CLASSIFICATION_MODEL=gpt-4
   export OPENAI_API_KEY=sk-...
   ```

### Retrieval Quality Issues

**Problem**: Wrong emails returned or missing relevant results

**Debug steps:**
1. Verify hybrid search is active:
   ```sql
   -- Check search_vector exists
   SELECT COUNT(*) FROM messages WHERE search_vector IS NOT NULL;
   ```

2. Check cross-encoder loading:
   ```bash
   # Look for this on startup
   grep "Loaded cross-encoder" logs/backend.log
   ```

3. Adjust hybrid weights:
   ```python
   # In semantic.py, modify weights:
   results = storage.hybrid_search(
       query_text=query,
       query_embedding=embedding,
       vector_weight=0.7,   # Increase for more semantic
       keyword_weight=0.3,  # Increase for more exact matching
   )
   ```

### Answer Quality Issues

**Problem**: Vague or incorrect answers

**Debug steps:**
1. Check email context length:
   ```python
   # Verify full bodies being used
   emails = storage.search_by_sender("uber", limit=5)
   for email in emails:
       body = email.get_body_text()
       print(f"Body length: {len(body)} chars")
   ```

2. Review LLM prompt:
   ```bash
   # Enable debug logging to see full prompts
   export LOG_LEVEL=DEBUG
   # Look for [LLM PROCESSOR] Prompt lines
   ```

3. Increase limit if answer incomplete:
   ```python
   # User said "last 10" but only got 5
   # Check if number extraction is working:
   handler._extract_number_from_query("last 10 emails")
   # Should return 10
   ```

### Performance Issues

**Problem**: Queries too slow

**Timings breakdown:**
- Classification: 5-15s (olmo2:7b), <1s (GPT-4)
- Parameter extraction: 3-8s (olmo2:7b), <1s (GPT-4)
- Database query: <100ms (indexed)
- Hybrid search: <500ms
- Cross-encoder reranking: 100-500ms
- Answer generation: 10-30s (olmo2:7b), 1-3s (GPT-4)

**Optimization options:**
1. Use faster LLM for classification:
   ```bash
   export CLASSIFICATION_MODEL=gpt-4o-mini
   ```

2. Reduce reranking candidates:
   ```python
   # In semantic.py
   results = storage.hybrid_search(..., retrieval_k=25)  # Was 50
   ```

---

## Key Files Reference

| Component | File | Purpose |
|-----------|------|---------|
| API Endpoint | `backend/src/api.py` | POST /api/query entry point |
| RAG Engine | `backend/src/services/rag_engine.py` | Orchestrates pipeline |
| Query Classifier | `backend/src/services/query_classifier.py` | Intent detection |
| Prompts | `backend/src/services/prompt_templates.py` | All LLM prompts |
| LLM Processor | `backend/src/services/llm_processor.py` | Multi-provider LLM abstraction |
| Sender Handler | `backend/src/services/query_handlers/sender.py` | Search by sender + number extraction |
| Semantic Handler | `backend/src/services/query_handlers/semantic.py` | Hybrid search + reranking |
| Storage | `backend/src/storage/postgres_storage.py` | Database queries, hybrid search |
| Message Model | `backend/src/models/message.py` | Email body extraction |
| Context Builder | `backend/src/services/context_builder.py` | Format emails for LLM |
| Migration | `backend/src/storage/migrations/001_add_fulltext_search.sql` | Full-text search setup |

---

## Summary

The mail-organizer query pipeline processes user questions through:

1. **Classification** (intent-based) → routes to appropriate handler
2. **Parameter Extraction** → extracts sender, dates, labels, limits, etc.
3. **Retrieval** → hybrid search (vector + keyword) with reranking
4. **Context Building** → full email bodies + chat history
5. **Answer Generation** → natural language response from LLM

**Key improvements implemented:**
- ✅ Intent-based classification (65-line prompt, handles contextual queries naturally)
- ✅ Number extraction (respects "last 10" in queries)
- ✅ Hybrid search (catches both semantic + exact matches)
- ✅ Cross-encoder reranking (improves precision)
- ✅ Full email context (2000 chars vs 160-char snippet)
- ✅ Chat history integration (all handlers resolve pronouns)

**Performance gains:**
- Classification: 82s → 5-15s (with olmo2:7b)
- Answer quality: Vague → Accurate and detailed
- Query handling: Context-aware with pronoun resolution

**Result**: Fast, accurate, context-aware email search and question answering.
