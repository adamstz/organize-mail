# Setup Guide for 8GB Systems

## Recommended: Gemma 2B

For a 2-core 8GB VM, **Gemma 2B** is the best choice:
- ✅ Only uses ~1.7GB RAM
- ✅ Good classification accuracy
- ✅ Fast inference
- ✅ Google's optimized small model

## Quick Setup

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Start Ollama server (in background)
ollama serve &

# 3. Pull Gemma 2B model
ollama pull gemma:2b

# 4. Test classification
PYTHONPATH=backend LLM_MODEL=gemma:2b python backend/examples/test_llm_providers.py

# 5. Run on your emails
PYTHONPATH=backend LLM_MODEL=gemma:2b python -m src.jobs.classify_messages --limit 10
```

## Alternative Models for 8GB Systems

| Model | RAM Usage | Accuracy | Speed | Notes |
|-------|-----------|----------|-------|-------|
| **gemma:2b** | 1.7GB | ⭐⭐⭐⭐ | Fast | **Recommended** |
| phi3 | 2.3GB | ⭐⭐⭐⭐⭐ | Medium | May OOM on 8GB (use if you have 12GB+) |
| tinyllama | 637MB | ⭐⭐ | Very Fast | Too small, poor accuracy |

## What NOT to Use

❌ **llama3** (4.7GB) - Will run out of memory  
❌ **mistral** (4.1GB) - Will run out of memory  
❌ **tinyllama** (637MB) - Too inaccurate, copies template examples

## Test Results (Gemma 2B)

```
Test Case 1:
  Subject: URGENT: Invoice #12345 Payment Due
  Result: Labels: ['finance'], Priority: high ✅

Test Case 2:
  Subject: Security Alert: Unusual Login Detected
  Result: Labels: ['security'], Priority: normal ✅

Test Case 3:
  Subject: Team Meeting Tomorrow at 3pm
  Result: Labels: ['meetings'], Priority: normal ✅

Test Case 4:
  Subject: Weekend Sale - 50% Off!
  Result: Labels: ['shopping'], Priority: normal ✅
```

## Auto-Start Ollama on Boot (Optional)

If systemd is available:
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

If not (like in this dev container):
```bash
# Add to your shell rc file (.bashrc or .zshrc)
echo 'ollama serve > /tmp/ollama.log 2>&1 &' >> ~/.bashrc
```

## Memory Management Tips

If you experience slowdowns:

1. **Reduce context window** (edit Modelfile):
```bash
# Create custom Modelfile
cat > Modelfile <<EOF
FROM gemma:2b
PARAMETER num_ctx 2048
EOF

# Create optimized model
ollama create gemma-light -f Modelfile

# Use it
export LLM_MODEL=gemma-light
```

2. **Close other applications** to free RAM

3. **Monitor usage**:
```bash
# Watch memory while classifying
watch -n 1 free -h
```

## Performance Expectations

On a 2-core 8GB VM with Gemma 2B:
- Classification speed: ~2-5 emails/second
- Memory usage: ~2GB total (model + overhead)
- Accuracy: Good for common categories
- First request: Slower (model loading)
- Subsequent: Fast (model stays in memory)

## Troubleshooting

### "Connection refused" error
```bash
# Check if Ollama is running
ps aux | grep ollama

# Start it
ollama serve &
```

### "Out of memory" errors
```bash
# Check available memory
free -h

# If low, use smaller model
ollama pull tinyllama  # Less accurate but very small
export LLM_MODEL=tinyllama
```

### Slow first classification
This is normal - the model loads into memory on first use. Subsequent classifications will be much faster.

## Production Deployment

For production on 8GB systems:

1. Set default model in environment:
```bash
export LLM_MODEL=gemma:2b
```

2. Ensure Ollama starts on boot (see above)

3. Monitor memory usage:
```bash
# Set up alerts if memory > 90%
```

4. Consider batch processing instead of real-time for large volumes

5. If you need better accuracy and have budget, use OpenAI API instead:
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."
# No local memory usage, pay per request (~$0.0005/email)
```
