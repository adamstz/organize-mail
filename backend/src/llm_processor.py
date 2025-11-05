"""Local LLM processor for message categorization.

This module provides pluggable LLM-based classification with multiple backends:
1. OpenAI API (GPT-3.5/4)
2. Anthropic API (Claude)
3. Ollama (local models via HTTP API)
4. External command (custom LLM scripts)
5. Rule-based fallback (keyword matching)

Configuration via environment variables:
- LLM_PROVIDER: "openai", "anthropic", "ollama", "command", or "rules" (default: auto-detect)
- OPENAI_API_KEY: OpenAI API key (if using OpenAI)
- ANTHROPIC_API_KEY: Anthropic API key (if using Anthropic)
- OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
- ORGANIZE_MAIL_LLM_CMD: External command to run (if using command provider)
- LLM_MODEL: Model name (default: gpt-3.5-turbo for OpenAI, claude-3-haiku for Anthropic, llama3 for Ollama)
"""
from typing import Any, Dict, Optional
import os
import json
import shlex
import subprocess
import urllib.request
import urllib.error


class LLMProcessor:
    def __init__(self, config: Dict | None = None):
        self.config = config or {}
        self.provider = self._detect_provider()
        self.model = self._get_model_name()

    def _detect_provider(self) -> str:
        """Auto-detect which LLM provider to use based on env vars."""
        provider = os.environ.get("LLM_PROVIDER", "").lower()
        if provider in ("openai", "anthropic", "ollama", "command", "rules"):
            return provider
        
        # Auto-detect based on available API keys or running services
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if self._is_ollama_running():
            return "ollama"
        if os.environ.get("ORGANIZE_MAIL_LLM_CMD"):
            return "command"
        
        return "rules"  # fallback to keyword-based

    def _is_ollama_running(self) -> bool:
        """Check if Ollama is running and accessible."""
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _get_model_name(self) -> str:
        """Get the model name from env or use provider defaults."""
        model = os.environ.get("LLM_MODEL")
        if model:
            return model
        
        # Provider defaults
        if self.provider == "openai":
            return "gpt-3.5-turbo"
        elif self.provider == "anthropic":
            return "claude-3-haiku-20240307"
        elif self.provider == "ollama":
            return "llama3"
        
        return ""

    def categorize_message(self, subject: str, body: str) -> Dict:
        """Return a classification dict for a message.

        Example return: {"labels": ["finance", "important"], "priority": "high"}
        """
        try:
            if self.provider == "openai":
                return self._categorize_openai(subject, body)
            elif self.provider == "anthropic":
                return self._categorize_anthropic(subject, body)
            elif self.provider == "ollama":
                return self._categorize_ollama(subject, body)
            elif self.provider == "command":
                return self._categorize_command(subject, body)
        except Exception as e:
            # Log the error and fall back to rules
            print(f"LLM categorization failed ({self.provider}): {e}")
        
        # Fallback to rule-based
        return self._rule_based(subject, body)

    def _categorize_openai(self, subject: str, body: str) -> Dict:
        """Use OpenAI API for classification."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        client = openai.OpenAI(api_key=api_key)
        
        prompt = self._build_classification_prompt(subject, body)
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an email classification assistant. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        
        content = response.choices[0].message.content.strip()
        return self._parse_llm_response(content)

    def _categorize_anthropic(self, subject: str, body: str) -> Dict:
        """Use Anthropic API for classification."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = self._build_classification_prompt(subject, body)
        
        message = client.messages.create(
            model=self.model,
            max_tokens=200,
            temperature=0.3,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        content = message.content[0].text.strip()
        return self._parse_llm_response(content)

    def _categorize_ollama(self, subject: str, body: str) -> Dict:
        """Use Ollama API for classification."""
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        
        prompt = self._build_classification_prompt(subject, body)
        
        # Ollama chat API payload
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an email classification assistant. Return only valid JSON with no explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "format": "json",  # Request JSON output format
            "options": {
                "temperature": 0.3,
                "num_predict": 200,
            }
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
            content = result.get("message", {}).get("content", "")
            return self._parse_llm_response(content)

    def _categorize_command(self, subject: str, body: str) -> Dict:
        """Use external command for classification."""
        cmd = os.environ.get("ORGANIZE_MAIL_LLM_CMD")
        if not cmd:
            raise ValueError("ORGANIZE_MAIL_LLM_CMD not set")
        
        inp = json.dumps({"subject": subject, "body": body}, ensure_ascii=False).encode("utf-8")
        args = shlex.split(cmd)
        proc = subprocess.run(args, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {proc.returncode}")
        
        out = proc.stdout.decode("utf-8").strip()
        return json.loads(out)

    def _build_classification_prompt(self, subject: str, body: str) -> str:
        """Build a structured prompt for LLM classification."""
        # Truncate body to avoid token limits
        body_truncated = body[:2000] if body else ""
        
        return f"""Classify this email into categories and assign a priority level.

Email to classify:
Subject: {subject}
Body: {body_truncated}

Instructions:
- Choose the most relevant category labels from: finance, security, meetings, personal, work, shopping, social, news, promotions, spam
- Assign priority: "high" (urgent/important), "normal" (routine), or "low" (can wait)
- Return ONLY a JSON object in this exact format:

{{"labels": ["category1", "category2"], "priority": "normal"}}

Do not include explanations or markdown. Only output valid JSON."""

    def _parse_llm_response(self, content: str) -> Dict:
        """Parse LLM response, handling common formatting issues."""
        # Try to extract JSON from markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        
        # Handle common LLM variations
        # 1. "label" (singular) instead of "labels" (plural)
        if "label" in result and "labels" not in result:
            label_value = result["label"]
            # Check if it's a comma-separated string
            if isinstance(label_value, str):
                result["labels"] = [l.strip() for l in label_value.split(",") if l.strip()]
            else:
                result["labels"] = [label_value] if label_value else []
            del result["label"]
        
        # 2. Ensure labels is a list
        if "labels" not in result:
            result["labels"] = []
        elif not isinstance(result["labels"], list):
            # Convert single string to list
            result["labels"] = [result["labels"]] if result["labels"] else []
        
        # 3. Ensure priority exists and is valid
        if "priority" not in result:
            result["priority"] = "normal"
        
        # Normalize priority to lowercase
        if isinstance(result.get("priority"), str):
            result["priority"] = result["priority"].lower()
            if result["priority"] not in ("high", "normal", "low"):
                result["priority"] = "normal"
        
        return result

    def _rule_based(self, subject: str, body: str) -> Dict:
        """A simple, local heuristic classifier used as a fallback.

        This is intentionally small: it looks for keywords and maps them to
        labels/priority. Replace with a proper LLM call in production.
        """
        text = (subject or "") + "\n" + (body or "")
        text_lower = text.lower()
        labels = []
        priority = "normal"

        if any(k in text_lower for k in ["invoice", "payment", "receipt", "bill"]):
            labels.append("finance")
        if any(k in text_lower for k in ["password", "login", "security", "account"]):
            labels.append("security")
            priority = "high"
        if any(k in text_lower for k in ["urgent", "asap", "immediately"]):
            priority = "high"
        if any(k in text_lower for k in ["meeting", "schedule", "calendar"]):
            labels.append("meetings")

        return {"labels": labels, "priority": priority}

