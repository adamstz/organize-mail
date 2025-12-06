# RAG Engine Refactoring Status

**Date:** December 3, 2025  
**Branch:** `wip`  
**Status:** Code complete, tests need to be run

## Summary

Refactored the monolithic `rag_engine.py` (1442 lines) into modular components for better maintainability.

## Changes Made

### 1. Storage Layer - New Methods Added

**Files modified:**
- `backend/src/storage/storage_interface.py` - Added 8 new abstract methods
- `backend/src/storage/postgres_storage.py` - Implemented all 8 methods + `_row_to_mail_message()` helper
- `backend/src/storage/memory_storage.py` - Implemented all 8 methods

**New methods:**
- `search_by_sender(sender, limit)` - Find emails from a specific sender
- `search_by_attachment(has_attachment, limit)` - Find emails with/without attachments
- `search_by_keywords(keywords, limit)` - Search emails by keywords in subject/body
- `count_by_topic(topic)` - Count emails matching a topic
- `get_daily_email_stats(days)` - Get email counts per day
- `get_top_senders(limit)` - Get most frequent senders
- `get_total_message_count()` - Total email count
- `get_unread_count()` - Count of unread emails

### 2. Query Handlers Package (NEW)

**Location:** `backend/src/services/query_handlers/`

| File | Class | Purpose |
|------|-------|---------|
| `__init__.py` | - | Package exports |
| `base.py` | `QueryHandler` | Abstract base with common methods |
| `conversation.py` | `ConversationHandler` | Greetings, help requests |
| `aggregation.py` | `AggregationHandler` | Statistics, counting queries |
| `sender.py` | `SenderHandler` | Search by sender |
| `attachment.py` | `AttachmentHandler` | Search by attachment |
| `classification.py` | `ClassificationHandler` | Label-based queries |
| `temporal.py` | `TemporalHandler` | Time-based queries |
| `semantic.py` | `SemanticHandler` | Vector search queries |

**Base class provides:**
- `_build_response()` - Standardized response format
- `_format_sources()` - Convert emails to source metadata
- `_call_llm()` - LangChain LLM invocation
- `_call_llm_simple()` - Quick extraction calls

### 3. Query Classifier (NEW)

**File:** `backend/src/services/query_classifier.py`

- `QueryClassifier` class with `detect_query_type()` method
- Uses LLM classification with heuristic fallback
- Routes to: conversation, aggregation, search-by-sender, search-by-attachment, classification, temporal, filtered-temporal, semantic

### 4. Prompt Templates - Updated

**File:** `backend/src/services/prompt_templates.py`

Added/updated prompts:
- `TOPIC_EXTRACTION_PROMPT` (new)
- `SENDER_EXTRACTION_PROMPT` (updated)
- `KEYWORD_EXTRACTION_PROMPT` (updated)

### 5. RAG Engine - Replaced

**File:** `backend/src/services/rag_engine.py`

- Reduced from ~1442 lines to ~170 lines
- Now acts as orchestrator only
- Uses dict mapping query types → handler instances
- Delegates classification to `QueryClassifier`

**Backup:** `backend/src/services/rag_engine_old.py` (delete after tests pass)

### 6. Services Init - Updated

**File:** `backend/src/services/__init__.py`

- Added `QueryClassifier` to exports

## Remaining Tasks

1. **Run tests** - Verify refactoring works:
   ```bash
   cd backend
   make test
   # or
   LLM_PROVIDER=rules pytest tests/ -v
   ```

2. **Delete backup** - Once tests pass:
   ```bash
   rm backend/src/services/rag_engine_old.py
   ```

3. **Integration testing** - Test RAG queries via API:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/query \
     -H "Content-Type: application/json" \
     -d '{"question":"What emails did I receive last week?","top_k":5}'
   ```

## Architecture After Refactor

```
rag_engine.py (orchestrator, ~170 lines)
    ├── query_classifier.py (routing logic)
    └── query_handlers/
        ├── base.py (abstract interface)
        ├── conversation.py
        ├── aggregation.py
        ├── sender.py
        ├── attachment.py
        ├── classification.py
        ├── temporal.py
        └── semantic.py

storage/
    ├── storage_interface.py (8 new methods)
    ├── postgres_storage.py (implementations)
    └── memory_storage.py (implementations)

prompt_templates.py (centralized prompts)
```

## Notes

- All prompts are centralized in `prompt_templates.py` - handlers import from there
- Storage methods use `_row_to_mail_message()` helper to avoid duplication
- Memory storage has full implementations (not stubs) for testing
- Terminal tool had issues (`ENOPRO` errors) - may need to run tests manually
