from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel

from . import storage
from .llm_processor import LLMProcessor

app = FastAPI(title="organize-mail backend")

# Allow CORS from common dev server origins used by Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/messages")
async def get_messages(limit: int = 50, offset: int = 0) -> dict:
    """Return messages from storage as JSON-serializable dicts with pagination metadata.

    Query params:
        - limit: max messages to return (default 50)
        - offset: skip this many results (default 0)
    
    Returns:
        {
            "data": [...],
            "total": N,
            "limit": 50,
            "offset": 0
        }
    """
    msgs = storage.list_messages_dicts(limit=limit, offset=offset)
    total = len(storage.get_message_ids())
    return {
        "data": msgs,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/{message_id}")
async def get_message(message_id: str) -> dict:
    """Get a single message by ID with its classification data."""
    msg = storage.get_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg.to_dict()


@app.get("/messages/{message_id}/classifications")
async def get_message_classifications(message_id: str) -> List[dict]:
    """Get all classification records for a message (historical)."""
    # Verify message exists
    msg = storage.get_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    records = storage.list_classification_records_for_message(message_id)
    return [r.to_dict() for r in records]


@app.get("/messages/{message_id}/classification/latest")
async def get_latest_classification(message_id: str) -> Optional[dict]:
    """Get the most recent classification for a message."""
    # Verify message exists
    msg = storage.get_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    classification = storage.get_latest_classification(message_id)
    if not classification:
        raise HTTPException(status_code=404, detail="No classification found for this message")
    
    return classification


@app.get("/stats")
async def get_stats() -> dict:
    """Get classification statistics."""
    all_message_ids = storage.get_message_ids()
    unclassified_ids = storage.get_unclassified_message_ids()
    classified_count = storage.count_classified_messages()
    total_count = len(all_message_ids)
    
    # Count by priority
    messages = storage.list_messages(limit=1000)
    priority_counts = {"High": 0, "Normal": 0, "Low": 0, "Unclassified": 0}
    label_counts = {}
    
    for msg in messages:
        if msg.priority:
            priority_key = msg.priority.capitalize()
            # Map old "Medium" to "Normal"
            if priority_key == "Medium":
                priority_key = "Normal"
            if priority_key in priority_counts:
                priority_counts[priority_key] += 1
            else:
                priority_counts[priority_key] = 1
        else:
            priority_counts["Unclassified"] += 1
        
        # Count labels
        if msg.classification_labels:
            for label in msg.classification_labels:
                label_counts[label] = label_counts.get(label, 0) + 1
    
    return {
        "total_messages": total_count,
        "classified_messages": classified_count,
        "unclassified_messages": len(unclassified_ids),
        "priority_counts": priority_counts,
        "label_counts": label_counts,
    }


@app.get("/labels")
async def get_labels(min_count: int = 3) -> dict:
    """Get all unique classification labels with their counts.
    
    Args:
        min_count: Minimum number of occurrences to include a label (default: 3)
    """
    # Use efficient database query instead of fetching all messages
    all_counts = storage.get_label_counts()
    
    # Filter by minimum count to exclude rare/one-off labels
    filtered_counts = {label: count for label, count in all_counts.items() if count >= min_count}
    
    # Sort by count descending
    sorted_labels = sorted(filtered_counts.items(), key=lambda x: x[1], reverse=True)
    
    return {
        "labels": [{"name": label, "count": count} for label, count in sorted_labels]
    }


@app.get("/messages/filter/priority/{priority}")
async def filter_by_priority(priority: str, limit: int = 50, offset: int = 0) -> dict:
    """Get messages filtered by priority (high, medium, low, unclassified)."""
    if priority.lower() == "unclassified":
        # Use database-level filtering for unclassified messages
        messages, total = storage.list_unclassified_messages(limit=limit, offset=offset)
    else:
        # Use database-level filtering with index on priority
        messages, total = storage.list_messages_by_priority(priority, limit=limit, offset=offset)
    
    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/label/{label}")
async def filter_by_label(label: str, limit: int = 50, offset: int = 0) -> dict:
    """Get messages filtered by classification label."""
    # Use database-level filtering with GIN index on classification_labels
    messages, total = storage.list_messages_by_label(label, limit=limit, offset=offset)
    
    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/classified")
async def filter_classified(limit: int = 50, offset: int = 0) -> dict:
    """Get only classified messages."""
    # Use database-level filtering with index on latest_classification_id
    messages, total = storage.list_classified_messages(limit=limit, offset=offset)
    
    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/unclassified")
async def filter_unclassified(limit: int = 50, offset: int = 0) -> dict:
    """Get only unclassified messages."""
    # Use database-level filtering
    messages, total = storage.list_unclassified_messages(limit=limit, offset=offset)
    
    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/models")
async def list_models() -> dict:
    """List available LLM models from Ollama."""
    import os
    import urllib.request
    import json
    
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    
    try:
        req = urllib.request.Request(f"{ollama_host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            models = [{"name": m["name"], "size": m["size"]} for m in data.get("models", [])]
            return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


class ReclassifyRequest(BaseModel):
    model: Optional[str] = None


@app.post("/messages/{message_id}/reclassify")
async def reclassify_message(message_id: str, request: ReclassifyRequest) -> dict:
    """Reclassify a message using the specified model."""
    import os
    import logging
    
    logger = logging.getLogger("uvicorn")
    logger.info(f"[RECLASSIFY] Starting reclassification for message_id={message_id} with model={request.model}")
    
    # Get the message
    msg = storage.get_message_by_id(message_id)
    if not msg:
        logger.error(f"[RECLASSIFY] Message not found: {message_id}")
        raise HTTPException(status_code=404, detail="Message not found")
    
    logger.info(f"[RECLASSIFY] Found message: subject='{msg.subject[:50]}...'")
    
    # Set model if provided
    if request.model:
        os.environ["LLM_MODEL"] = request.model
        logger.info(f"[RECLASSIFY] Using model: {request.model}")
    
    # Classify using LLM
    processor = LLMProcessor()
    subject = msg.subject or ""
    # Try to extract body from payload, fallback to snippet
    body = ""
    if msg.payload and isinstance(msg.payload, dict):
        # Try to get body from payload
        parts = msg.payload.get('parts', [])
        if parts:
            for part in parts:
                if isinstance(part, dict) and part.get('mimeType') == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        import base64
                        try:
                            body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                            logger.info(f"[RECLASSIFY] Extracted body from parts: {len(body)} chars")
                            break
                        except:
                            pass
        # Fallback to body.data at root level
        if not body and 'body' in msg.payload:
            body_data = msg.payload['body'].get('data', '')
            if body_data:
                import base64
                try:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                    logger.info(f"[RECLASSIFY] Extracted body from root: {len(body)} chars")
                except:
                    pass
    # Final fallback to snippet
    if not body:
        body = msg.snippet or ""
        logger.info(f"[RECLASSIFY] Using snippet as body: {len(body)} chars")
    
    try:
        logger.info(f"[RECLASSIFY] Calling LLM with subject='{subject[:50]}...' body={len(body)} chars")
        result = processor.categorize_message(subject, body)
        logger.info(f"[RECLASSIFY] LLM returned: labels={result.get('labels')}, priority={result.get('priority')}, summary='{result.get('summary', '')[:50]}...'")
        
        # Create a new classification record
        from datetime import datetime, timezone
        import uuid
        from .models.classification_record import ClassificationRecord
        
        classification_record = ClassificationRecord(
            id=str(uuid.uuid4()),
            message_id=message_id,
            labels=result.get("labels", []),
            priority=result.get("priority", "normal"),
            summary=result.get("summary", ""),
            model=request.model or processor.model,
            created_at=datetime.now(timezone.utc)
        )
        
        logger.info(f"[RECLASSIFY] Created classification record: id={classification_record.id}")
        
        # Save the classification record
        storage.save_classification_record(classification_record)
        logger.info(f"[RECLASSIFY] Saved classification record to database")
        
        # Update the message to point to this latest classification
        storage.update_message_latest_classification(message_id, classification_record.id)
        logger.info(f"[RECLASSIFY] Updated message latest_classification_id to {classification_record.id}")
        
        logger.info(f"[RECLASSIFY] Reclassification complete for message_id={message_id}")

        
        return {
            "success": True,
            "message_id": message_id,
            "classification": {
                "labels": classification_record.labels,
                "priority": classification_record.priority,
                "summary": classification_record.summary,
                "model": classification_record.model
            }
        }
    except Exception as e:
        logger.error(f"[RECLASSIFY] Error during reclassification: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reclassification failed: {str(e)}")
