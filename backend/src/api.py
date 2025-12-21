from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import logging
import asyncio
from collections import deque
from datetime import datetime

from . import storage
from .services import LLMProcessor, EmbeddingService, RAGQueryEngine
from .sync_manager import get_sync_manager

app = FastAPI(title="organize-mail backend")

# Allow CORS from common dev server origins used by Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    storage.init_db()
    logging.info("Database initialized")


# Log buffer for real-time viewing
log_buffer = deque(maxlen=500)
log_subscribers: List[WebSocket] = []


class LogBufferHandler(logging.Handler):
    """Custom logging handler that stores logs in memory and broadcasts to WebSocket clients."""

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record)
            }
            log_buffer.append(log_entry)

            # Broadcast to all connected WebSocket clients
            disconnected = []
            for ws in log_subscribers:
                try:
                    asyncio.create_task(ws.send_json(log_entry))
                except Exception:
                    disconnected.append(ws)

            # Remove disconnected clients
            for ws in disconnected:
                if ws in log_subscribers:
                    log_subscribers.remove(ws)
        except Exception:
            pass


# Set up logging handlers
log_handler = LogBufferHandler()
log_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)

# Add console handler for terminal output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Add handlers to root logger and uvicorn logger
logging.getLogger().addHandler(log_handler)
logging.getLogger().addHandler(console_handler)
logging.getLogger("uvicorn").addHandler(log_handler)
logging.getLogger("uvicorn.access").addHandler(log_handler)

# Set root logger level
logging.getLogger().setLevel(logging.INFO)

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@app.get("/health")
async def health():
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    log_subscribers.append(websocket)
    logger.info(f"New log viewer connected. Total subscribers: {len(log_subscribers)}")

    try:
        # Send existing log buffer to new client (make a copy to avoid mutation issues)
        existing_logs = list(log_buffer)
        for log_entry in existing_logs:
            await websocket.send_json(log_entry)

        # Keep connection alive and wait for disconnect
        while True:
            # Just wait for messages (we don't expect any from client)
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in log_subscribers:
            log_subscribers.remove(websocket)
        logger.info(f"Log viewer disconnected. Remaining subscribers: {len(log_subscribers)}")
    except Exception as e:
        if websocket in log_subscribers:
            log_subscribers.remove(websocket)
        logger.error(f"WebSocket error: {e}")


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """Get recent logs as JSON array."""
    logs = list(log_buffer)
    logger.debug(f"Logs requested: returning {min(limit, len(logs))} of {len(logs)} entries")
    return logs[-limit:] if limit < len(logs) else logs


class FrontendLogRequest(BaseModel):
    level: str
    message: str
    timestamp: str


@app.post("/api/frontend-log")
async def receive_frontend_log(log_entry: FrontendLogRequest):
    """Receive log entries from the frontend and add them to the log buffer."""
    try:
        # Create a log entry that matches our format
        log_data = {
            "timestamp": log_entry.timestamp,
            "level": log_entry.level,
            "logger": "frontend",
            "message": log_entry.message
        }
        log_buffer.append(log_data)
        logger.debug(f"Frontend log received: {log_entry.message}, subscribers: {len(log_subscribers)}")

        # Broadcast to all connected WebSocket clients
        disconnected = []
        for ws in log_subscribers:
            try:
                await ws.send_json(log_data)
                logger.debug(f"Sent log to WebSocket client")
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                disconnected.append(ws)

        # Remove disconnected clients
        for ws in disconnected:
            if ws in log_subscribers:
                log_subscribers.remove(ws)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error receiving frontend log: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/messages")
async def get_messages(limit: int = 50, offset: int = 0) -> dict:
    """Return messages from storage with HTML bodies included.

    Query params:
        - limit: max messages to return (default 50)
        - offset: skip this many results (default 0)

    Returns:
        {
            "data": [...],  # Each message includes 'html' and 'plain_text' fields
            "total": N,
            "limit": 50,
            "offset": 0
        }
    """
    import time
    from bs4 import BeautifulSoup
    import re

    start_time = time.time()
    logger.info(f"GET /messages - limit={limit}, offset={offset}")

    msgs = storage.list_messages_dicts(limit=limit, offset=offset)
    total = len(storage.get_message_ids())

    # Add HTML body to each message
    for msg in msgs:
        html_body = ""
        payload = msg.get('payload')

        # Handle payload deserialization if needed
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = None

        # Extract HTML from payload
        if payload and isinstance(payload, dict):
            html_body = _extract_html_from_payload(payload, logger)

        # Generate plain text from HTML
        plain_text = ""
        if html_body:
            try:
                soup = BeautifulSoup(html_body, 'html.parser')
                for tag in soup.find_all(['style', 'script', 'head']):
                    tag.decompose()
                plain_text = soup.get_text(separator=' ', strip=True)
                plain_text = re.sub(r'\s+', ' ', plain_text).strip()
            except Exception:
                plain_text = msg.get('snippet', '')
        else:
            plain_text = msg.get('snippet', '')

        # Add to message dict
        msg['html'] = html_body
        msg['plain_text'] = plain_text

    query_time = time.time() - start_time
    logger.info(f"GET /messages - returned {len(msgs)}/{total} messages in {query_time:.3f}s")
    return {
        "data": msgs,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/{message_id}")
async def get_message(message_id: str) -> dict:
    """Get a single message by ID with its classification data."""
    logger.debug(f"GET /messages/{message_id}")
    msg = storage.get_message_by_id(message_id)
    if not msg:
        logger.warning(f"Message not found: {message_id}")
        raise HTTPException(status_code=404, detail="Message not found")
    logger.debug(f"Found message: {msg.subject[:50]}")
    return msg.to_dict()


def _extract_html_from_payload(payload: dict, logger) -> str:
    """Recursively extract HTML body from Gmail MIME payload structure.

    Gmail emails often have nested multipart structures like:
    multipart/alternative
      |- text/plain
      |- multipart/related
          |- text/html
          |- image

    This function collects ALL text/html parts and returns the most complete one.

    Args:
        payload: Gmail message payload dict
        logger: Logger instance

    Returns:
        Decoded HTML string (longest/most complete), or empty string if not found
    """
    import base64

    if not isinstance(payload, dict):
        logger.error(f"[MIME EXTRACTION] Payload is not a dict: {type(payload)}")
        return ""

    # Collect ALL HTML parts instead of returning the first one
    html_parts = []

    def collect_html_recursive(part, depth=0):
        """Recursively collect all HTML parts."""
        if not isinstance(part, dict):
            logger.warning(f"{'  ' * depth}Part is not a dict: {type(part)}")
            return

        mime_type = part.get('mimeType', '')
        logger.debug(f"{'  ' * depth}Checking part: mimeType={mime_type}")

        # If this part is text/html, extract and collect it
        if mime_type == 'text/html':
            body_data = part.get('body', {}).get('data', '')
            if body_data:
                try:
                    html = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                    html_parts.append(html)
                    logger.info(f"{'  ' * depth}✓ Found HTML part: {len(html)} chars")
                except Exception as e:
                    logger.error(f"{'  ' * depth}Error decoding HTML body: {e}", exc_info=True)

        # Recurse into child parts
        child_parts = part.get('parts', [])
        if child_parts:
            logger.debug(f"{'  ' * depth}Recursing into {len(child_parts)} child parts")
            for child_part in child_parts:
                collect_html_recursive(child_part, depth + 1)

    # Start recursive collection from root payload
    logger.info(f"[MIME EXTRACTION] Starting HTML extraction from payload")
    try:
        collect_html_recursive(payload)
    except Exception as e:
        logger.error(f"[MIME EXTRACTION] Error during recursive collection: {e}", exc_info=True)

    # Return the LONGEST HTML part (most complete)
    if html_parts:
        logger.info(f"[MIME EXTRACTION] Found {len(html_parts)} HTML part(s) with sizes: {[len(p) for p in html_parts]}")
        longest = max(html_parts, key=len)
        logger.info(f"[MIME EXTRACTION] Selected longest HTML: {len(longest)} chars")

        # Log if there are images detected for debugging
        if '<img' in longest:
            img_count = longest.count('<img')
            logger.info(f"[MIME EXTRACTION] HTML contains {img_count} <img> tag(s)")
            print(f"✓ Found {img_count} <img> tags in extracted HTML")
        else:
            logger.warning(f"[MIME EXTRACTION] No <img> tags found in HTML")
            print("⚠ WARNING: No <img> tags found in extracted HTML!")

        return longest

    logger.warning(f"[MIME EXTRACTION] No HTML parts found in payload")
    return ""


@app.get("/messages/{message_id}/body")
async def get_message_body(message_id: str) -> dict:
    """Get email body HTML and metadata.

    Returns raw HTML extracted from the email payload.
    Frontend is responsible for sanitization with DOMPurify.

    Returns:
        {
            "html": "...",  # Raw HTML from email
            "plain_text": "...",  # Plain text version
            "snippet": "..."  # Email snippet
        }
    """
    logger.debug(f"GET /messages/{message_id}/body")

    # Get the message
    msg = storage.get_message_by_id(message_id)
    if not msg:
        logger.warning(f"Message not found: {message_id}")
        raise HTTPException(status_code=404, detail="Message not found")

    # Extract HTML body from payload using recursive search
    html_body = ""
    payload = msg.payload

    # Handle payload deserialization if it's stored as JSON string
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
            logger.debug(f"Deserialized payload from JSON string")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to deserialize payload: {e}")
            payload = None

    if payload and not isinstance(payload, dict):
        logger.error(f"Payload is not a dict after deserialization - type: {type(payload)}")
        payload = None

    if payload:
        html_body = _extract_html_from_payload(payload, logger)

    # Generate plain text from HTML or use snippet
    plain_text = ""
    if html_body:
        # Simple HTML to text conversion
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html_body, 'html.parser')
            # Remove script and style tags
            for tag in soup.find_all(['style', 'script', 'head']):
                tag.decompose()
            plain_text = soup.get_text(separator=' ', strip=True)
            # Clean up whitespace
            import re
            plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        except Exception as e:
            logger.error(f"Error converting HTML to plain text: {e}")
            plain_text = msg.snippet or ""
    else:
        plain_text = msg.snippet or ""

    logger.info(f"Extracted email body for {message_id}: {len(html_body)} chars HTML, {len(plain_text)} chars plain text")

    return {
        "html": html_body,
        "plain_text": plain_text,
        "snippet": msg.snippet or ""
    }


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
    logger.debug(f"GET /messages/{message_id}/classification/latest")
    # Verify message exists
    msg = storage.get_message_by_id(message_id)
    if not msg:
        logger.warning(f"Message not found: {message_id}")
        raise HTTPException(status_code=404, detail="Message not found")

    classification = storage.get_latest_classification(message_id)
    if not classification:
        logger.warning(f"No classification found for message: {message_id}")
        raise HTTPException(status_code=404, detail="No classification found for this message")

    return classification


@app.get("/stats")
async def get_stats() -> dict:
    """Get classification statistics."""
    logger.info("GET /stats - calculating statistics")
    all_message_ids = storage.get_message_ids()
    unclassified_ids = storage.get_unclassified_message_ids()
    classified_count = storage.count_classified_messages()
    total_count = len(all_message_ids)
    logger.debug(f"Stats: {classified_count}/{total_count} classified")

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
    logger.info(f"GET /labels - min_count={min_count}")
    # Use efficient database query instead of fetching all messages
    all_counts = storage.get_label_counts()

    # Filter by minimum count to exclude rare/one-off labels
    filtered_counts = {label: count for label, count in all_counts.items() if count >= min_count}

    # Sort by count descending
    sorted_labels = sorted(filtered_counts.items(), key=lambda x: x[1], reverse=True)
    logger.debug(f"Returning {len(sorted_labels)} labels")

    return {
        "labels": [{"name": label, "count": count} for label, count in sorted_labels]
    }


@app.get("/messages/filter/priority/{priority}")
async def filter_by_priority(priority: str, limit: int = 50, offset: int = 0) -> dict:
    """Get messages filtered by priority (high, medium, low, unclassified)."""
    import time
    start_time = time.time()
    logger.info(f"GET /messages/filter/priority/{priority} - limit={limit}, offset={offset}")

    if priority.lower() == "unclassified":
        # Use database-level filtering for unclassified messages
        messages, total = storage.list_unclassified_messages(limit=limit, offset=offset)
    else:
        # Use database-level filtering with index on priority
        messages, total = storage.list_messages_by_priority(priority, limit=limit, offset=offset)

    query_time = time.time() - start_time
    logger.info(f"Priority filter returned {len(messages)}/{total} messages in {query_time:.3f}s")

    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/label/{label}")
async def filter_by_label(label: str, limit: int = 50, offset: int = 0) -> dict:
    """Get messages filtered by classification label."""
    import time
    start_time = time.time()
    logger.info(f"GET /messages/filter/label/{label} - limit={limit}, offset={offset}")

    # Use database-level filtering with GIN index on classification_labels
    messages, total = storage.list_messages_by_label(label, limit=limit, offset=offset)

    query_time = time.time() - start_time
    logger.info(f"Label filter returned {len(messages)}/{total} messages in {query_time:.3f}s")

    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/classified")
async def filter_classified(limit: int = 50, offset: int = 0) -> dict:
    """Get only classified messages."""
    logger.info(f"GET /messages/filter/classified - limit={limit}, offset={offset}")
    # Use database-level filtering with index on latest_classification_id
    messages, total = storage.list_classified_messages(limit=limit, offset=offset)
    logger.debug(f"Found {len(messages)}/{total} classified messages")

    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/unclassified")
async def filter_unclassified(limit: int = 50, offset: int = 0) -> dict:
    """Get only unclassified messages."""
    logger.info(f"GET /messages/filter/unclassified - limit={limit}, offset={offset}")
    # Use database-level filtering
    messages, total = storage.list_unclassified_messages(limit=limit, offset=offset)
    logger.debug(f"Found {len(messages)}/{total} unclassified messages")

    return {
        "data": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/messages/filter/advanced")
async def filter_advanced(
    priority: Optional[str] = None,
    labels: Optional[str] = None,  # Comma-separated list of labels
    status: Optional[str] = None,  # 'classified', 'unclassified', or 'all'
    limit: int = 50,
    offset: int = 0
) -> dict:
    """Advanced filtering with multiple criteria (priority, labels, status).

    Query params:
        - priority: 'high', 'normal', or 'low'
        - labels: comma-separated labels (e.g., 'work,urgent')
        - status: 'classified', 'unclassified', or 'all'
        - limit: max results (default 50)
        - offset: pagination offset (default 0)
    """
    import time
    start_time = time.time()

    logger.info(
        f"GET /messages/filter/advanced - priority={priority}, "
        f"labels={labels}, status={status}, limit={limit}, offset={offset}"
    )

    # Parse labels
    label_list = None
    if labels:
        label_list = [label.strip() for label in labels.split(',') if label.strip()]

    # Determine classified filter
    classified = None
    if status == 'classified':
        classified = True
    elif status == 'unclassified':
        classified = False

    # Use optimized database-level filtering
    fetch_start = time.time()

    # Check if storage backend supports the optimized method
    if hasattr(storage, 'list_messages_by_filters'):
        messages, total = storage.list_messages_by_filters(
            priority=priority,
            labels=label_list,
            classified=classified,
            limit=limit,
            offset=offset
        )
        fetch_time = time.time() - fetch_start
        print(
            f"[ADVANCED FILTER] Database query completed in {fetch_time:.3f}s - "
            f"found {len(messages)}/{total} messages"
        )

        # Serialize to dict
        serialize_start = time.time()
        result_data = [m.to_dict() for m in messages]
        serialize_time = time.time() - serialize_start
        print(f"[ADVANCED FILTER] Serialization took {serialize_time:.3f}s")

        total_time = time.time() - start_time
        print(
            f"[ADVANCED FILTER] Total request time: {total_time:.3f}s "
            f"(db_query={fetch_time:.3f}s, serialize={serialize_time:.3f}s)"
        )

        return {
            "data": result_data,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # Fallback to Python filtering for storage backends that don't support combined filters
    print(
        "[ADVANCED FILTER] Using fallback Python filtering "
        "(storage backend doesn't support list_messages_by_filters)"
    )
    fetch_limit = 2000

    if status == 'unclassified':
        messages, _ = storage.list_unclassified_messages(limit=fetch_limit, offset=0)
    else:
        messages, _ = storage.list_classified_messages(limit=fetch_limit, offset=0)
    fetch_time = time.time() - fetch_start
    print(f"[ADVANCED FILTER] Fetched {len(messages)} messages in {fetch_time:.3f}s")

    # Apply filters in Python
    filter_start = time.time()
    filtered = messages

    # Filter by priority
    if priority:
        filtered = [m for m in filtered if m.priority and m.priority.lower() == priority.lower()]
        print(f"[ADVANCED FILTER] After priority filter: {len(filtered)} messages")

    # Filter by labels (must have ALL specified labels)
    if label_list:
        filtered = [
            m for m in filtered
            if m.classification_labels and all(
                any(el.lower() == sl.lower() for el in m.classification_labels)
                for sl in label_list
            )
        ]
        print(f"[ADVANCED FILTER] After labels filter ({label_list}): {len(filtered)} messages")

    filter_time = time.time() - filter_start
    print(f"[ADVANCED FILTER] Filtering took {filter_time:.3f}s")

    # Apply pagination
    total_filtered = len(filtered)
    paginated = filtered[offset:offset + limit]

    # Serialize to dict
    serialize_start = time.time()
    result_data = [m.to_dict() for m in paginated]
    serialize_time = time.time() - serialize_start
    print(f"[ADVANCED FILTER] Serialization took {serialize_time:.3f}s")

    total_time = time.time() - start_time
    print(
        f"[ADVANCED FILTER] Total request time: {total_time:.3f}s "
        f"(fetch={fetch_time:.3f}s, filter={filter_time:.3f}s, serialize={serialize_time:.3f}s)"
    )

    return {
        "data": result_data,
        "total": total_filtered,
        "limit": limit,
        "offset": offset
    }


@app.get("/models")
async def list_models() -> dict:
    """List available LLM models from Ollama."""
    import json
    import os
    import urllib.request

    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    try:
        req = urllib.request.Request(f"{ollama_host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            models = [{"name": m["name"], "size": m["size"]} for m in data.get("models", [])]
            return {"models": models}
    except urllib.error.URLError as e:
        logger.warning(f"Ollama not available: {e}")
        raise HTTPException(status_code=503, detail="Ollama service not available. Please start Ollama.")
    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return {"models": [], "error": str(e)}


class SetModelRequest(BaseModel):
    """Request model for setting the active LLM model."""
    model: str


@app.post("/api/set-model")
async def set_model(request: SetModelRequest) -> dict:
    """Set the active LLM model for all subsequent operations."""
    import os

    try:
        os.environ["LLM_MODEL"] = request.model
        logger.info(f"[MODEL SELECTION] Changed model to: {request.model}")
        return {
            "success": True,
            "model": request.model,
            "message": f"Model changed to {request.model}"
        }
    except Exception as e:
        logger.error(f"[MODEL SELECTION] Error setting model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/current-model")
async def get_current_model() -> dict:
    """Get the currently active LLM model."""
    import os

    current_model = os.getenv("LLM_MODEL", "")
    provider = os.getenv("LLM_PROVIDER", "ollama")

    return {
        "model": current_model,
        "provider": provider
    }


@app.post("/api/ollama/start")
async def start_ollama() -> dict:
    """Start the Ollama service."""
    import subprocess
    import os

    logger.info("Starting Ollama service...")
    try:
        # Try to start Ollama in the background
        if os.name == 'nt':  # Windows
            subprocess.Popen(['ollama', 'serve'], creationflags=subprocess.CREATE_NO_WINDOW)
        else:  # Unix/Linux/Mac
            subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        logger.info("Ollama service start command issued")
        return {"status": "started", "message": "Ollama service is starting"}
    except FileNotFoundError:
        logger.error("Ollama executable not found")
        raise HTTPException(status_code=404, detail="Ollama not installed. Please install Ollama from https://ollama.ai")
    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start Ollama: {str(e)}")


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
                        except Exception:
                            pass
        # Fallback to body.data at root level
        if not body and 'body' in msg.payload:
            body_data = msg.payload['body'].get('data', '')
            if body_data:
                import base64
                try:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                    logger.info(f"[RECLASSIFY] Extracted body from root: {len(body)} chars")
                except Exception:
                    pass
    # Final fallback to snippet
    if not body:
        body = msg.snippet or ""
        logger.info(f"[RECLASSIFY] Using snippet as body: {len(body)} chars")

    try:
        logger.info(f"[RECLASSIFY] Calling LLM with subject='{subject[:50]}...' body={len(body)} chars")
        result = processor.categorize_message(subject, body)
        logger.info(
            f"[RECLASSIFY] LLM returned: labels={result.get('labels')}, "
            f"priority={result.get('priority')}, summary='{result.get('summary', '')[:50]}...'"
        )

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

        logger.info("[RECLASSIFY] Reclassification complete for message_id=%s", message_id)

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


# ==================== RAG ENDPOINTS ====================

# Lazy initialization of RAG components
_rag_engine: Optional[RAGQueryEngine] = None


def get_rag_engine() -> RAGQueryEngine:
    """Get or initialize the RAG query engine."""
    global _rag_engine
    if _rag_engine is None:
        from .storage.storage import get_storage_backend
        storage_backend = get_storage_backend()
        embedder = EmbeddingService()
        llm = LLMProcessor()
        _rag_engine = RAGQueryEngine(storage_backend, embedder, llm)
    return _rag_engine


async def generate_session_title(chat_session_id: str, first_message: str):
    """Background task to generate a title for a new chat session.

    Args:
        chat_session_id: The session ID to update
        first_message: The first user message to base the title on
    """
    try:
        logger.info(f"[TITLE GEN] Starting title generation for session {chat_session_id}")

        # Get LLM processor
        rag_engine = get_rag_engine()
        llm = rag_engine.llm

        # Generate title
        title = await llm.generate_chat_title(first_message)

        # Update session title
        storage.update_chat_session_title(chat_session_id, title)

        logger.info(f"[TITLE GEN] ✓ Updated session {chat_session_id} with title: '{title}'")

    except Exception as e:
        logger.error(f"[TITLE GEN] ✗ Failed to generate title for session {chat_session_id}: {e}", exc_info=True)
        # Don't raise - this is a background task, failure shouldn't affect the main flow


# ==================== SYNC ENDPOINTS ====================


@app.get("/api/sync-status")
async def get_sync_status() -> dict:
    """Get current sync status including Gmail vs DB counts and progress."""
    logger.info("GET /api/sync-status")
    sync_manager = get_sync_manager()
    status = sync_manager.get_sync_status()
    logger.debug(f"Sync status: {status}")
    return status


@app.post("/api/sync/pull")
async def sync_pull() -> dict:
    """Start pulling new messages from Gmail INBOX."""
    logger.info("POST /api/sync/pull - Starting pull operation")
    sync_manager = get_sync_manager()

    started = sync_manager.start_pull()

    if not started:
        logger.warning("Pull operation already running")
        raise HTTPException(status_code=409, detail="Pull operation already in progress")

    logger.info("Pull operation started successfully")
    return {
        "status": "started",
        "message": "Pull operation started in background"
    }


@app.post("/api/sync/classify")
async def sync_classify() -> dict:
    """Start classifying and embedding unclassified messages."""
    logger.info("POST /api/sync/classify - Starting classify and embed operation")
    sync_manager = get_sync_manager()

    started = sync_manager.start_classify()

    if not started:
        logger.warning("Classify operation already running")
        raise HTTPException(status_code=409, detail="Classify operation already in progress")

    logger.info("Classify and embed operation started successfully")
    return {
        "status": "started",
        "message": "Classify and embed operation started in background"
    }


class QueryRequest(BaseModel):
    """Request model for RAG queries."""
    question: str
    chat_session_id: Optional[str] = None
    top_k: Optional[int] = 5
    similarity_threshold: Optional[float] = 0.5
    model: Optional[str] = None


class ChatSessionCreateRequest(BaseModel):
    """Request model for creating a new chat session."""
    title: Optional[str] = None


class ChatSessionUpdateRequest(BaseModel):
    """Request model for updating a chat session."""
    title: str


@app.post("/api/query")
async def query_emails(request: QueryRequest) -> dict:
    """Ask a question and get an answer based on email content.

    This uses RAG (Retrieval-Augmented Generation):
    1. Converts your question to a vector embedding
    2. Finds the most similar emails
    3. Uses an LLM to answer based on those emails

    Example request:
    {
        "question": "What invoices did I receive last month?",
        "session_id": "optional-session-uuid",
        "top_k": 5,
        "similarity_threshold": 0.5
    }
    """
    import logging
    import time
    logger = logging.getLogger("uvicorn")

    print("=" * 80)
    print(f"[API QUERY] Received query request")
    print(f"[API QUERY] Question: '{request.question}'")
    print(f"[API QUERY] Chat Session ID: {request.chat_session_id}")
    print(f"[API QUERY] Top K: {request.top_k}")
    print(f"[API QUERY] Similarity Threshold: {request.similarity_threshold}")

    logger.info(f"[RAG QUERY] Question: {request.question}, Chat Session: {request.chat_session_id}")

    start_time = time.time()

    try:
        # Track if this is the first message in the session (for title generation)
        is_first_message = False

        # Save user message to chat session if chat_session_id provided
        if request.chat_session_id:
            # Check if this is the first message
            messages = storage.get_chat_session_messages(request.chat_session_id, limit=1)
            is_first_message = len(messages) == 0

            storage.save_message_to_chat_session(
                chat_session_id=request.chat_session_id,
                role='user',
                content=request.question
            )

        print(f"[API QUERY] Getting RAG engine...")
        rag_engine = get_rag_engine()
        print(f"[API QUERY] RAG engine obtained successfully")
        print(f"[API QUERY] Model: {rag_engine.llm.provider}/{rag_engine.llm.model}")

        # Fetch chat history for context if chat_session_id is provided
        chat_history = []
        if request.chat_session_id:
            try:
                session_messages = storage.get_chat_session_messages(request.chat_session_id, limit=20)
                # Convert to the format expected by RAG engine: [{"role": "user/assistant", "content": "..."}]
                chat_history = [
                    {
                        "role": msg["role"],
                        "content": msg["content"]
                    }
                    for msg in session_messages
                    # Exclude the current message we're about to process
                    if not (msg["role"] == "user" and msg["content"] == request.question)
                ]
                print(f"[API QUERY] Loaded {len(chat_history)} previous messages for context")
            except Exception as e:
                logger.warning(f"[API QUERY] Failed to load chat history: {e}")
                chat_history = []

        print(f"[API QUERY] Calling RAG engine query...")
        result = rag_engine.query(
            question=request.question,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            chat_history=chat_history
        )

        # Save assistant response to chat session if chat_session_id provided
        if request.chat_session_id:
            storage.save_message_to_chat_session(
                chat_session_id=request.chat_session_id,
                role='assistant',
                content=result.get('answer', ''),
                sources=result.get('sources', []),
                confidence=result.get('confidence'),
                query_type=result.get('query_type')
            )

            # Generate title asynchronously if this is the first message
            if is_first_message:
                asyncio.create_task(generate_session_title(request.chat_session_id, request.question))

        elapsed_time = time.time() - start_time
        print(f"[API QUERY] ✓ Query completed in {elapsed_time:.2f}s")
        print(f"[API QUERY] Answer: {result.get('answer', 'No answer')[:100]}...")
        print(f"[API QUERY] Sources: {len(result.get('sources', []))}")
        print(f"[API QUERY] Confidence: {result.get('confidence', 'unknown')}")
        print(f"[API QUERY] Query type: {result.get('query_type', 'unknown')}")

        logger.info(f"[RAG QUERY] Answer generated with {len(result['sources'])} sources, confidence: {result['confidence']}")

        # Add chat_session_id to response
        if request.chat_session_id:
            result['chat_session_id'] = request.chat_session_id

        return result

    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"[API QUERY] ✗ Query failed after {elapsed_time:.2f}s: {str(e)}")
        logger.error(f"[RAG QUERY] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/api/embedding_status")
async def embedding_status() -> dict:
    """Get statistics about embedding coverage.

    Returns how many emails have been embedded and are ready for semantic search.
    """
    from .storage.storage import get_storage_backend

    backend = get_storage_backend()
    conn = backend.connect()
    cur = conn.cursor()

    # Count embedded messages
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE embedding IS NOT NULL) as single_embeddings,
            COUNT(*) FILTER (WHERE embedding_model IS NOT NULL AND embedding IS NULL) as chunked_embeddings
        FROM messages
    """)
    row = cur.fetchone()

    # Count chunks
    cur.execute("SELECT COUNT(*) as chunk_count FROM email_chunks")
    chunk_row = cur.fetchone()

    cur.close()
    conn.close()

    total = row[0]
    single = row[1]
    chunked = row[2]
    embedded = single + chunked
    chunks = chunk_row[0]

    return {
        "total_messages": total,
        "embedded_messages": embedded,
        "single_embeddings": single,
        "chunked_emails": chunked,
        "total_chunks": chunks,
        "coverage_percent": round((embedded / total * 100) if total > 0 else 0, 1),
        "ready_for_search": embedded > 0
    }


# Chat session endpoints
@app.post("/api/chat-sessions")
async def create_chat_session(request: ChatSessionCreateRequest) -> dict:
    """Create a new chat session."""
    logger.info(f"Creating new chat session with title: {request.title}")

    from datetime import datetime, timezone
    chat_session_id = storage.create_chat_session(title=request.title)

    # Return full session object to match list endpoint format
    return {
        "id": chat_session_id,
        "title": request.title or "New Chat",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message_count": 0
    }


@app.get("/api/chat-sessions")
async def list_chat_sessions(limit: int = 50, offset: int = 0) -> dict:
    """List all chat sessions ordered by most recent."""
    logger.info(f"Listing chat sessions: limit={limit}, offset={offset}")

    sessions = storage.list_chat_sessions(limit=limit, offset=offset)

    return {
        "chat_sessions": sessions,
        "total": len(sessions),
        "limit": limit,
        "offset": offset
    }


@app.get("/api/chat-sessions/{chat_session_id}/messages")
async def get_chat_session_messages(chat_session_id: str, limit: int = 100, offset: int = 0) -> dict:
    """Get all messages for a specific chat session."""
    logger.info(f"Getting messages for chat session {chat_session_id}: limit={limit}, offset={offset}")

    messages = storage.get_chat_session_messages(chat_session_id=chat_session_id, limit=limit, offset=offset)

    return {
        "chat_session_id": chat_session_id,
        "messages": messages,
        "total": len(messages),
        "limit": limit,
        "offset": offset
    }


@app.delete("/api/chat-sessions/{chat_session_id}")
async def delete_chat_session(chat_session_id: str) -> dict:
    """Delete a chat session and all its messages."""
    logger.info(f"Deleting chat session {chat_session_id}")

    storage.delete_chat_session(chat_session_id=chat_session_id)

    return {
        "chat_session_id": chat_session_id,
        "message": "Chat session deleted successfully"
    }


@app.patch("/api/chat-sessions/{chat_session_id}")
async def update_chat_session(chat_session_id: str, request: ChatSessionUpdateRequest) -> dict:
    """Update a chat session's title."""
    logger.info(f"Updating chat session {chat_session_id} title to: {request.title}")

    storage.update_chat_session_title(chat_session_id=chat_session_id, title=request.title)

    return {
        "chat_session_id": chat_session_id,
        "title": request.title,
        "message": "Chat session updated successfully"
    }
