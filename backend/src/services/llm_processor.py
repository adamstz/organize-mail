"""LangChain-based LLM processor for message categorization.

This module provides pluggable LLM-based classification with multiple backends via LangChain:
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
from typing import Dict, Optional
import os
import json
import shlex
import subprocess
import urllib.request
import urllib.error
import logging
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import SystemMessage, HumanMessage
from ..classification_labels import ALLOWED_LABELS
from .prompt_templates import (
    CLASSIFICATION_SYSTEM_MESSAGE,
    build_classification_prompt,
    CHAT_TITLE_GENERATION_PROMPT,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class LLMProcessor:
    """LangChain-powered LLM processor for email classification and RAG."""

    # Shared LLM configuration
    TEMPERATURE = 0.3
    MAX_TOKENS = 200
    TIMEOUT = 60  # Increased for slower local models

    def __init__(self, config: Dict | None = None):
        self.config = config or {}
        self.provider = self._detect_provider()
        self.model = self._get_model_name()
        self.llm: Optional[BaseChatModel] = self._initialize_llm()

        # Log LLM configuration
        logger.info(f"[LLM INIT] Initialized LLM processor - Provider: {self.provider}, Model: {self.model}")

        # Set up output parser for JSON responses
        self.json_parser = JsonOutputParser()

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
            return self._get_best_ollama_model()

        return ""

    def _get_best_ollama_model(self) -> str:
        """Get the best available Ollama model by selecting the largest one.

        Returns:
            The name of the best available model, or 'llama3' as fallback.
        """
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
                models = data.get("models", [])

                if not models:
                    logger.warning("[LLM] No Ollama models found, using fallback 'llama3'")
                    return "llama3"

                # Sort by size (descending) to get the most capable model
                sorted_models = sorted(models, key=lambda m: m.get("size", 0), reverse=True)
                best_model = sorted_models[0]["name"]

                logger.info(f"[LLM] Auto-selected Ollama model: {best_model} (size: {sorted_models[0].get('size', 0)} bytes)")
                return best_model

        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[LLM] Failed to fetch Ollama models: {e}, using fallback 'llama3'")
            return "llama3"

    def _initialize_llm(self) -> Optional[BaseChatModel]:
        """Initialize LangChain LLM based on provider.

        Returns:
            BaseChatModel instance for LangChain providers, None for command/rules
        """
        if self.provider == "rules":
            return None

        if self.provider == "command":
            # Command provider doesn't use LangChain
            return None

        try:
            if self.provider == "openai":
                from langchain_openai import ChatOpenAI
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("[LLM INIT] OPENAI_API_KEY not set, cannot initialize LangChain")
                    return None
                return ChatOpenAI(
                    model=self.model,
                    temperature=self.TEMPERATURE,
                    max_tokens=self.MAX_TOKENS,
                    api_key=api_key
                )

            elif self.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    logger.warning("[LLM INIT] ANTHROPIC_API_KEY not set, cannot initialize LangChain")
                    return None
                return ChatAnthropic(
                    model=self.model,
                    temperature=self.TEMPERATURE,
                    max_tokens=self.MAX_TOKENS,
                    api_key=api_key
                )

            elif self.provider == "ollama":
                from langchain_ollama import ChatOllama
                host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
                return ChatOllama(
                    model=self.model,
                    temperature=self.TEMPERATURE,
                    num_predict=self.MAX_TOKENS,
                    base_url=host
                )

            else:
                logger.warning(f"[LLM INIT] Unknown provider '{self.provider}', no LangChain LLM created")
                return None

        except ImportError as e:
            logger.error(f"[LLM INIT] Failed to import LangChain provider: {e}")
            raise ImportError(
                f"LangChain {self.provider} integration not installed. "
                f"Run: pip install langchain-{self.provider}"
            )

    def invoke(self, prompt: str) -> str:
        """Invoke LLM with a simple string prompt (for RAG queries).

        Args:
            prompt: The prompt string

        Returns:
            LLM response as string
        """
        if self.llm:
            # Use LangChain
            logger.debug(f"[LLM INVOKE] Using LangChain with {self.provider}/{self.model}")
            messages = [HumanMessage(content=prompt)]
            response = self.llm.invoke(messages)
            return response.content.strip()
        elif self.provider == "ollama":
            # Fallback to direct Ollama API
            logger.debug(f"[LLM INVOKE] Using direct Ollama API")
            return self._call_ollama_direct(prompt)
        elif self.provider == "rules":
            # Rules provider fallback - return a simple response for testing
            logger.debug(f"[LLM INVOKE] Rules provider - returning fallback response")
            return "Based on the emails provided, I can help answer your question."
        else:
            raise RuntimeError(f"No LLM available for provider '{self.provider}'")

    def categorize_message(self, subject: str, body: str) -> Dict:
        """Return a classification dict for a message.

        Example return: {"labels": ["finance", "important"], "priority": "high", "summary": "Invoice payment reminder"}
        """
        logger.debug(f"[LLM CATEGORIZE] Starting categorization")
        logger.debug(f"[LLM CATEGORIZE] Provider: {self.provider}, Model: {self.model}")
        logger.debug(f"[LLM CATEGORIZE] Subject: '{subject[:50]}...'")

        # Use rule-based for rules provider
        if self.provider == "rules":
            logger.debug(f"[LLM CATEGORIZE] Using rule-based classification")
            return self._rule_based(subject, body)

        # For non-rules providers, use LLM
        logger.debug(f"[LLM CATEGORIZE] Using LLM-based classification")
        try:
            if self.llm:
                # Use LangChain
                result = self._categorize_with_langchain(subject, body)
            else:
                # Fallback for command provider
                result = self._categorize_with_llm(subject, body)

            logger.info(f"[LLM CATEGORIZE] ✓ Classification successful: {result.get('labels', [])}")
            return result
        except Exception as e:
            logger.error(f"[LLM CATEGORIZE] ✗ Classification failed: {e}")
            raise

    def _categorize_with_langchain(self, subject: str, body: str) -> Dict:
        """Use LangChain to categorize email."""
        prompt = build_classification_prompt(subject, body)

        messages = [
            SystemMessage(content=CLASSIFICATION_SYSTEM_MESSAGE),
            HumanMessage(content=prompt)
        ]

        logger.debug(f"[LLM LANGCHAIN] Invoking LLM...")
        response = self.llm.invoke(messages)
        content = response.content.strip()

        logger.debug(f"[LLM LANGCHAIN] Response length: {len(content)} chars")

        # Parse the response into our standard format
        return self._parse_llm_response(content)

    def _categorize_with_llm(self, subject: str, body: str) -> Dict:
        """Common LLM categorization flow: build prompt → call provider → parse response."""
        prompt = build_classification_prompt(subject, body)

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
                {"role": "system", "content": CLASSIFICATION_SYSTEM_MESSAGE},
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
        """Call Ollama API (deprecated - use _call_ollama_direct instead)."""
        return self._call_ollama_direct(prompt)

    def _call_ollama_direct(self, prompt: str) -> str:
        """Call Ollama API directly and return raw response text."""
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_MESSAGE},
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
                result["labels"] = [
                    label.strip() for label in label_value.split(",") if label.strip()
                ]
            else:
                result["labels"] = [label_value] if label_value else []
            del result["label"]

        # 2. Ensure labels is a list
        if "labels" not in result:
            result["labels"] = []
        elif not isinstance(result["labels"], list):
            # Convert single string to list
            result["labels"] = [result["labels"]] if result["labels"] else []

        # 3. Filter labels to only allowed ones (normalize to lowercase)
        if result.get("labels"):
            normalized_labels = []
            for label in result["labels"]:
                label_lower = str(label).lower().strip()
                if label_lower in ALLOWED_LABELS:
                    normalized_labels.append(label_lower)
            result["labels"] = normalized_labels

        # 4. Ensure priority exists and is valid
        if "priority" not in result:
            result["priority"] = "normal"

        # Normalize priority to lowercase
        if isinstance(result.get("priority"), str):
            result["priority"] = result["priority"].lower()
            if result["priority"] not in ("high", "normal", "low"):
                result["priority"] = "normal"

        # 5. Ensure summary exists
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

        # Job-related keywords
        if any(k in text_lower for k in ["thank you for applying", "application received", "applied for"]):
            labels.append("job-application")
        if any(k in text_lower for k in ["interview", "schedule a call", "would like to meet"]):
            labels.append("job-interview")
        if any(k in text_lower for k in ["job offer", "offer letter", "pleased to offer"]):
            labels.append("job-offer")
            priority = "high"
        if any(k in text_lower for k in ["unfortunately", "not moving forward", "position has been filled"]):
            labels.append("job-rejection")
        if any(k in text_lower for k in ["jobs match", "new job", "job alert", "apply now"]):
            labels.append("job-ad")

        # Generate simple summary from subject
        summary = subject[:100] if subject else "No subject"

        return {"labels": labels, "priority": priority, "summary": summary}

    async def generate_chat_title(self, first_message: str) -> str:
        """Generate a concise title for a chat session based on the first user message.

        Args:
            first_message: The first user message in the chat session

        Returns:
            A concise title (3-7 words) summarizing the conversation topic
        """
        import asyncio

        logger.debug(f"[LLM TITLE] Generating title for message: '{first_message[:50]}...'")

        # For rules provider, generate simple keyword-based title
        if self.provider == "rules":
            words = first_message.split()[:5]
            title = " ".join(words)
            if len(title) > 50:
                title = title[:47] + "..."
            logger.debug(f"[LLM TITLE] Rules-based title: '{title}'")
            return title or "New Chat"

        # Build prompt from template
        prompt = CHAT_TITLE_GENERATION_PROMPT.format(first_message=first_message)

        try:
            # Run LLM invocation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            title = await loop.run_in_executor(None, self.invoke, prompt)

            # Clean up the response
            title = title.strip().strip('"').strip("'")

            # Ensure reasonable length
            if len(title) > 60:
                title = title[:57] + "..."

            logger.info(f"[LLM TITLE] Generated title: '{title}'")
            return title

        except Exception as e:
            logger.error(f"[LLM TITLE] Failed to generate title: {e}")
            # Fallback to truncated first message
            words = first_message.split()[:5]
            fallback = " ".join(words)
            if len(fallback) > 50:
                fallback = fallback[:47] + "..."
            return fallback or "New Chat"
