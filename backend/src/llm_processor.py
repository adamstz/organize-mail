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
    # Shared LLM configuration
    SYSTEM_MESSAGE = "You are an email classification assistant. Return only valid JSON with no explanations."
    TEMPERATURE = 0.3
    MAX_TOKENS = 200
    TIMEOUT = 60  # Increased for slower local models
    
    def __init__(self, config: Dict | None = None):
        self.config = config or {}
        self.provider = self._detect_provider()
        self.model = self._get_model_name()

    def _detect_provider(self) -> str:
        """Auto-detect which LLM provider to use based on env vars."""
        provider = os.environ.get("LLM_PROVIDER", "").lower()
        
        # If explicitly set to rules (for testing), allow it
        if provider == "rules":
            return provider
        
        # Check for explicit provider setting
        if provider in ("openai", "anthropic", "ollama", "command"):
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
        
        # No LLM provider available - raise error
        raise RuntimeError(
            "No LLM provider configured. Please set one of:\n"
            "  - OPENAI_API_KEY for OpenAI\n"
            "  - ANTHROPIC_API_KEY for Anthropic/Claude\n"
            "  - Start Ollama server (ollama serve)\n"
            "  - ORGANIZE_MAIL_LLM_CMD for custom command\n"
            "  - LLM_PROVIDER=rules for testing only (keyword-based)"
        )

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

        Example return: {"labels": ["finance", "important"], "priority": "high", "summary": "Invoice payment reminder"}
        """
        # Use rule-based for rules provider
        if self.provider == "rules":
            return self._rule_based(subject, body)
        
        # For non-rules providers, don't fall back - let the error propagate
        return self._categorize_with_llm(subject, body)

    def _categorize_with_llm(self, subject: str, body: str) -> Dict:
        """Common LLM categorization flow: build prompt → call provider → parse response."""
        prompt = self._build_classification_prompt(subject, body)
        
        # Get raw LLM response based on provider
        if self.provider == "openai":
            content = self._call_openai(prompt)
        elif self.provider == "anthropic":
            content = self._call_anthropic(prompt)
        elif self.provider == "ollama":
            content = self._call_ollama(prompt)
        elif self.provider == "command":
            content = self._call_command(subject, body)  # command uses different input format
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
        
        # Parse the response into our standard format
        return self._parse_llm_response(content)

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API and return raw response text."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            temperature=self.TEMPERATURE,
            max_tokens=self.MAX_TOKENS,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API and return raw response text."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text.strip()

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API and return raw response text."""
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "format": "json",  # Request JSON output format
            "options": {
                "temperature": self.TEMPERATURE,
                "num_predict": self.MAX_TOKENS,
            }
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as response:
            result = json.load(response)
            return result.get("message", {}).get("content", "")

    def _call_command(self, subject: str, body: str) -> str:
        """Call external command and return raw response text.
        
        Note: Command provider uses different input format (subject/body dict)
        rather than pre-built prompt, so it returns JSON directly.
        """
        cmd = os.environ.get("ORGANIZE_MAIL_LLM_CMD")
        if not cmd:
            raise ValueError("ORGANIZE_MAIL_LLM_CMD not set")
        
        inp = json.dumps({"subject": subject, "body": body}, ensure_ascii=False).encode("utf-8")
        args = shlex.split(cmd)
        proc = subprocess.run(args, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.TIMEOUT)
        
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {proc.returncode}")
        
        return proc.stdout.decode("utf-8").strip()


    def _build_classification_prompt(self, subject: str, body: str) -> str:
        """Build a structured prompt for LLM classification."""
        # Truncate body to avoid token limits
        body_truncated = body[:2000] if body else ""
        
        return f"""Classify this email into categories, assign a priority level, and provide a brief summary.

Email to classify:
Subject: {subject}
Body: {body_truncated}

Instructions:
- Choose the most relevant category labels from: finance, banking, investments, security, authentication, meetings, appointments, personal, work, career, job, job-application, job-applied, job-pending, job-interview, job-rejected, job-offer, job-followup, shopping, ecommerce, social, entertainment, news, newsletters, promotions, marketing, spam, travel, health, education, legal, taxes, receipts, notifications, updates, alerts, support, bills, insurance
- Job labels guide: use 'job-application' for any job-related email, then add specific status like 'job-applied' (confirmation you applied), 'job-pending' (awaiting response), 'job-interview' (interview scheduled), 'job-rejected' (rejection), 'job-offer' (offer received), 'job-followup' (follow-up communications)
- Assign priority: "high" (urgent/important), "normal" (routine), or "low" (can wait)
- Write a brief summary (1-2 sentences) of the email's main purpose
- Return ONLY a JSON object in this exact format:

{{"labels": ["category1", "category2"], "priority": "normal", "summary": "Brief description of the email"}}

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
        
        # 4. Ensure summary exists
        if "summary" not in result:
            result["summary"] = ""
        
        # Ensure summary is a string
        if not isinstance(result.get("summary"), str):
            result["summary"] = str(result.get("summary", ""))
        
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

        # Generate simple summary from subject
        summary = subject[:100] if subject else "No subject"

        return {"labels": labels, "priority": priority, "summary": summary}

