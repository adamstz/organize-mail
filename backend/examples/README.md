# LLM Provider Examples

This directory contains example scripts demonstrating how to use different LLM providers for email classification.

## Available Providers

The `LLMProcessor` supports multiple backends:

1. **OpenAI** - Uses GPT-3.5-turbo or GPT-4
2. **Anthropic** - Uses Claude models
3. **Ollama** - Local models via Ollama (llama3, mistral, etc.)
4. **Command** - External command/script (custom integrations)
5. **Rules** - Simple keyword-based fallback (no API needed)

## Quick Start

### 1. Rule-Based (No Setup Required)

```bash
PYTHONPATH=backend LLM_PROVIDER=rules python backend/examples/test_llm_providers.py
```

### 2. Custom Command (Using Dummy LLM)

```bash
PYTHONPATH=backend \
  ORGANIZE_MAIL_LLM_CMD="python backend/examples/dummy_llm.py" \
  LLM_PROVIDER=command \
  python backend/examples/test_llm_providers.py
```

### 3. Ollama (Local LLM - Recommended for Privacy)

**No wrapper script needed!** Just start Ollama and it works.

```bash
# 1. Install and start Ollama (if not already running)
ollama pull llama3

# 2. Run classification (auto-detects Ollama)
PYTHONPATH=backend python backend/examples/test_llm_providers.py
```

Or explicitly:
```bash
PYTHONPATH=backend LLM_PROVIDER=ollama python backend/examples/test_llm_providers.py
```

Optional: use a different model
```bash
export LLM_MODEL="mistral"
PYTHONPATH=backend LLM_PROVIDER=ollama python backend/examples/test_llm_providers.py
```

### 4. OpenAI

```bash
export OPENAI_API_KEY="sk-..."
PYTHONPATH=backend LLM_PROVIDER=openai python backend/examples/test_llm_providers.py
```

Optional: specify a different model
```bash
export LLM_MODEL="gpt-4"
```

### 5. Anthropic

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
PYTHONPATH=backend LLM_PROVIDER=anthropic python backend/examples/test_llm_providers.py
```

Optional: specify a different model
```bash
export LLM_MODEL="claude-3-opus-20240229"
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Provider to use: `openai`, `anthropic`, `ollama`, `command`, `rules` | Auto-detect based on API keys / running services |
| `LLM_MODEL` | Model name to use | Provider-specific defaults |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `ORGANIZE_MAIL_LLM_CMD` | External command for classification | - |

## Using Ollama (Recommended for Local/Private Use)

Ollama provides the best balance of privacy, cost, and ease-of-use. **No wrapper scripts needed** — the processor talks directly to Ollama's API.

### Quick Setup

1. **Install Ollama**: https://ollama.ai/
2. **Pull a model**:
   ```bash
   ollama pull llama3
   # or try other models: mistral, phi, codellama, etc.
   ```
3. **Verify it's running**:
   ```bash
   curl http://localhost:11434/api/tags
   ```
4. **Run classification** (auto-detects Ollama):
   ```bash
   PYTHONPATH=backend python -m src.jobs.classify_messages
   ```

### Benefits

- ✅ **Free** - No API costs
- ✅ **Private** - Data never leaves your machine
- ✅ **Fast** - Local inference (with GPU even faster)
- ✅ **No wrappers** - Native integration, just works
- ✅ **Auto-detection** - Processor checks if Ollama is running

### Recommended Models

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| `llama3` | 4.7GB | Fast | Excellent | Best all-around choice |
| `mistral` | 4.1GB | Fast | Great | Slightly faster, still very good |
| `phi` | 1.6GB | Very Fast | Good | Resource-constrained systems |
| `codellama` | 3.8GB | Fast | Great | Good at structured output |

### Custom Ollama Host

If running Ollama on a different machine or port:

```bash
export OLLAMA_HOST="http://192.168.1.100:11434"
PYTHONPATH=backend python -m src.jobs.classify_messages
```

## Using with Custom Commands (Advanced)

For other LLM setups (llama.cpp server, custom scripts, etc.), use the command provider.

For other LLM setups (llama.cpp server, custom scripts, etc.), use the command provider.

Example wrapper script for llama.cpp:

```bash
#!/bin/bash
# llama_cpp_classify.sh
INPUT=$(cat)
SUBJECT=$(echo "$INPUT" | jq -r '.subject')
BODY=$(echo "$INPUT" | jq -r '.body')

PROMPT="Classify this email. Return only JSON: {\"labels\": [...], \"priority\": \"high|normal|low\"}

Subject: $SUBJECT
Body: $BODY"

curl -s http://localhost:8080/completion -H "Content-Type: application/json" -d "{
  \"prompt\": \"$PROMPT\",
  \"temperature\": 0.3,
  \"max_tokens\": 200
}" | jq -r '.content' | grep -o '{.*}'
```

Use it:
```bash
chmod +x llama_cpp_classify.sh
PYTHONPATH=backend \
  ORGANIZE_MAIL_LLM_CMD="./llama_cpp_classify.sh" \
  LLM_PROVIDER=command \
  python backend/examples/test_llm_providers.py
```

## Classification Output Format

All providers return a dictionary with:

```python
{
    "labels": ["finance", "work", ...],  # List of category labels
    "priority": "high" | "normal" | "low"  # Priority level
}
```

### Standard Labels

- `finance` - Financial/billing emails
- `security` - Security alerts, password resets
- `meetings` - Calendar invites, meeting requests
- `personal` - Personal correspondence
- `work` - Work-related
- `shopping` - Order confirmations, shipping
- `social` - Social media notifications
- `news` - Newsletters, news alerts
- `promotions` - Marketing, sales
- `spam` - Unwanted mail

## Files

- `test_llm_providers.py` - Test script that runs classification on sample emails
- `dummy_llm.py` - Mock LLM for testing the command provider (no API needed)

## Integration with classify_messages Job

The classification job uses the same `LLMProcessor` with auto-detection:

```bash
# Auto-detect (checks for Ollama, then API keys, then falls back to rules)
PYTHONPATH=backend python -m src.jobs.classify_messages --limit 10

# Or force a specific provider
export LLM_PROVIDER=ollama
PYTHONPATH=backend python -m src.jobs.classify_messages --limit 10
```

With OpenAI:
```bash
export OPENAI_API_KEY="sk-..."
PYTHONPATH=backend python -m src.jobs.classify_messages --limit 10
```

The job will:
1. Fetch messages from storage
2. Classify each using the configured LLM provider
3. Save labels and priority to the message
4. Create a `ClassificationRecord` for audit history
