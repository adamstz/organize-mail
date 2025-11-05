# LLM Provider Quick Reference

## One-Line Setup

### Ollama (Recommended - Local, Private, Free)
```bash
ollama pull llama3 && PYTHONPATH=backend python -m src.jobs.classify_messages
```

### OpenAI
```bash
export OPENAI_API_KEY="sk-..." && PYTHONPATH=backend python -m src.jobs.classify_messages
```

### Anthropic
```bash
export ANTHROPIC_API_KEY="sk-ant-..." && PYTHONPATH=backend python -m src.jobs.classify_messages
```

### Rule-Based (No setup, keyword matching only)
```bash
PYTHONPATH=backend LLM_PROVIDER=rules python -m src.jobs.classify_messages
```

## Provider Auto-Detection Priority

1. Check `LLM_PROVIDER` env var (if set, use that)
2. Check for `OPENAI_API_KEY` → use OpenAI
3. Check for `ANTHROPIC_API_KEY` → use Anthropic
4. Check if Ollama is running on localhost:11434 → use Ollama
5. Check for `ORGANIZE_MAIL_LLM_CMD` → use command
6. Fall back to rule-based

## Configuration Matrix

| Provider | Required Setup | Cost | Privacy | Speed | Quality |
|----------|---------------|------|---------|-------|---------|
| **Ollama** | Install Ollama + pull model | Free | 100% private | Fast | Excellent |
| **OpenAI** | API key | ~$0.0005/email | Cloud | Very fast | Excellent |
| **Anthropic** | API key | ~$0.001/email | Cloud | Very fast | Excellent |
| **Command** | Custom script | Varies | Varies | Varies | Varies |
| **Rules** | None | Free | 100% private | Instant | Basic |

## Environment Variables

```bash
# Provider selection (auto-detects if not set)
export LLM_PROVIDER="ollama"  # or: openai, anthropic, command, rules

# Model selection (uses provider defaults if not set)
export LLM_MODEL="llama3"     # Ollama: llama3, mistral, phi, etc.
export LLM_MODEL="gpt-4"      # OpenAI: gpt-3.5-turbo, gpt-4, etc.
export LLM_MODEL="claude-3-opus-20240229"  # Anthropic

# API Keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Ollama (only if not using default localhost:11434)
export OLLAMA_HOST="http://192.168.1.100:11434"

# Custom command (for advanced use)
export ORGANIZE_MAIL_LLM_CMD="python my_llm_script.py"
```

## Testing Different Providers

Run the test script to see classification results:

```bash
# Test with Ollama
PYTHONPATH=backend LLM_PROVIDER=ollama python backend/examples/test_llm_providers.py

# Test with OpenAI
export OPENAI_API_KEY="sk-..."
PYTHONPATH=backend LLM_PROVIDER=openai python backend/examples/test_llm_providers.py

# Compare all available providers
for provider in rules ollama openai; do
  echo "=== Testing $provider ==="
  PYTHONPATH=backend LLM_PROVIDER=$provider python backend/examples/test_llm_providers.py | head -20
done
```

## Troubleshooting

### Ollama connection refused
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama (if installed)
ollama serve

# Or install: https://ollama.ai/
```

### OpenAI/Anthropic rate limits
```bash
# Reduce concurrency or add delays in classify_messages.py
# Or switch to Ollama for unlimited local use
export LLM_PROVIDER=ollama
```

### Wrong provider selected
```bash
# Force a specific provider
export LLM_PROVIDER=ollama

# Check what will be used
PYTHONPATH=backend python -c "from src.llm_processor import LLMProcessor; p = LLMProcessor(); print(f'Provider: {p.provider}, Model: {p.model}')"
```

## Production Recommendations

**For privacy-sensitive use:** Ollama (all data stays local)
**For best quality:** OpenAI GPT-4 or Anthropic Claude Opus
**For best cost/performance:** Ollama llama3 or OpenAI GPT-3.5-turbo
**For testing/development:** Rule-based (no setup)
**For mixed workload:** Auto-detection (falls back gracefully)
