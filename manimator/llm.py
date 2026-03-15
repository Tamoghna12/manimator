"""
LLM integration for automated storyboard generation.

Supports multiple providers (OpenAI, Anthropic, Google Gemini, ZhipuAI,
OpenAI-compatible) with lazy SDK imports so only the used provider's
package needs to be installed.

Usage:
    from manimator.llm import generate_storyboard, list_providers

    result = generate_storyboard(
        topic="How CRISPR works",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-...",
    )
"""

import json
import os
import re

from manimator.schema import Storyboard
from manimator.topic_templates import get_storyboard_prompt


# ── Provider Registry ────────────────────────────────────────────────────────

PROVIDERS = {
    "openai": {
        "models": ["gpt-4o", "gpt-4o-mini"],
        "default": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
        "default": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "google": {
        "models": ["gemini-2.5-flash", "gemini-2.0-flash"],
        "default": "gemini-2.5-flash",
        "env_key": "GOOGLE_API_KEY",
    },
    "zhipuai": {
        "models": ["glm-5", "glm-5-turbo", "glm-4.7", "glm-4.7-FlashX", "glm-4.7-Flash"],
        "default": "glm-5",
        "env_key": "ZHIPUAI_API_KEY",
    },
    "ollama": {
        "models": ["llama3.2", "llama3.1", "mistral", "qwen2.5", "gemma3", "phi4"],
        "default": "llama3.2",
        "env_key": "",
        "base_url": "http://localhost:11434/v1",
    },
    "openai_compatible": {
        "models": [],
        "default": "",
        "env_key": "OPENAI_API_KEY",
    },
}


# ── JSON Extraction ──────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output, stripping markdown fences and prose.

    Handles:
    - Clean JSON
    - ```json ... ``` fenced blocks
    - ``` ... ``` fenced blocks without language tag
    - Leading/trailing prose around JSON
    - Nested braces

    Raises ValueError if no valid JSON object is found.
    """
    # Try stripping markdown fences first
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # Try parsing the whole text directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost { ... } using brace counting
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    raise ValueError("Found JSON-like block but it failed to parse")

    raise ValueError("No complete JSON object found in LLM response")


# ── Provider Call Functions ──────────────────────────────────────────────────

def _call_openai(prompt: str, model: str, api_key: str, **kwargs) -> str:
    """Call OpenAI API. Lazy-imports openai SDK."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a scientific video storyboard generator. "
             "Output ONLY valid JSON matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def _call_anthropic(prompt: str, model: str, api_key: str, **kwargs) -> str:
    """Call Anthropic API. Lazy-imports anthropic SDK."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system="You are a scientific video storyboard generator. "
               "Output ONLY valid JSON matching the requested schema.",
        messages=[
            {"role": "user", "content": prompt},
        ],
    )
    return response.content[0].text


def _call_google(prompt: str, model: str, api_key: str, **kwargs) -> str:
    """Call Google Gemini API. Lazy-imports google-genai SDK."""
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=f"You are a scientific video storyboard generator. "
                 f"Output ONLY valid JSON matching the requested schema.\n\n{prompt}",
    )
    return response.text


def _call_zhipuai(prompt: str, model: str, api_key: str, **kwargs) -> str:
    """Call ZhipuAI (Z.AI) API. Uses OpenAI-compatible endpoint."""
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.z.ai/api/paas/v4/",
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a scientific video storyboard generator. "
             "Output ONLY valid JSON matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def _call_ollama(prompt: str, model: str, api_key: str = "", base_url: str = "", **kwargs) -> str:
    """Call Ollama local API. Uses OpenAI-compatible endpoint with JSON mode."""
    from openai import OpenAI

    url = base_url or "http://localhost:11434/v1"
    client = OpenAI(api_key=api_key or "ollama", base_url=url, timeout=300)

    system = (
        "You are a JSON generator. Your ONLY output must be a single raw JSON object. "
        "No markdown, no code fences, no explanations, no comments. "
        "Start your response with { and end with }."
    )

    try:
        # Try with JSON mode enforced (supported by most Ollama models)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception:
        # Fallback: some older models don't support response_format
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
    return response.choices[0].message.content


def _call_openai_compatible(
    prompt: str, model: str, api_key: str, base_url: str = "", **kwargs
) -> str:
    """Call an OpenAI-compatible API (Groq, Together, Ollama, etc.)."""
    from openai import OpenAI

    if not base_url:
        raise ValueError("base_url is required for openai_compatible provider")
    if not model:
        raise ValueError("model is required for openai_compatible provider")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a scientific video storyboard generator. "
             "Output ONLY valid JSON matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content


_CALLERS = {
    "openai": "_call_openai",
    "anthropic": "_call_anthropic",
    "google": "_call_google",
    "zhipuai": "_call_zhipuai",
    "ollama": "_call_ollama",
    "openai_compatible": "_call_openai_compatible",
}


# ── Public API ───────────────────────────────────────────────────────────────

def list_providers() -> dict[str, list[str]]:
    """Return {provider_name: [model_names]} for all registered providers."""
    return {name: info["models"] for name, info in PROVIDERS.items()}


def generate_storyboard(
    topic: str,
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    domain: str | None = None,
    structure: str = "explainer",
    format_type: str = "presentation",
    theme: str = "wong",
    base_url: str = "",
    max_retries: int = 1,
) -> dict:
    """Generate a validated storyboard dict from a topic using an LLM.

    Args:
        topic: The video topic (e.g. "How CRISPR works").
        provider: LLM provider key (openai, anthropic, google, zhipuai, openai_compatible).
        model: Model name. Falls back to provider default if omitted.
        api_key: API key. Falls back to env var if omitted.
        domain: Optional domain template key (e.g. biology_reel).
        structure: Story structure key (default: explainer).
        format_type: Video format (default: presentation).
        theme: Color theme (default: wong).
        base_url: Required for openai_compatible provider.
        max_retries: Number of retries on validation failure (default: 1).

    Returns:
        Validated storyboard dict ready for rendering.

    Raises:
        ValueError: Unknown provider, missing API key, or JSON extraction failure.
        pydantic.ValidationError: Storyboard schema validation failure after retries.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDERS.keys())}")

    info = PROVIDERS[provider]

    # Resolve API key (Ollama doesn't require one)
    if not api_key and info.get("env_key"):
        api_key = os.environ.get(info["env_key"], "")
    if not api_key and info.get("env_key"):
        raise ValueError(
            f"No API key for {provider}. Set {info['env_key']} env var or pass api_key."
        )

    # Resolve base_url (use provider default if not explicitly passed)
    if not base_url and info.get("base_url"):
        base_url = info["base_url"]

    # Resolve model
    if not model:
        model = info["default"]
        if not model:
            raise ValueError(f"No default model for {provider}. Specify --model.")

    # Build prompt
    prompt = get_storyboard_prompt(
        topic=topic,
        structure=structure,
        domain=domain,
        format_type=format_type,
        theme=theme,
    )

    # Look up caller dynamically so mock patching works in tests
    import manimator.llm as _self
    caller_name = _CALLERS[provider]
    caller = getattr(_self, caller_name)
    last_error = None

    for attempt in range(1 + max_retries):
        # On retry, append error feedback to prompt
        call_prompt = prompt
        if attempt > 0 and last_error:
            call_prompt += (
                f"\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
                f"Error: {last_error}\n"
                f"Please fix the JSON and try again. Output ONLY valid JSON."
            )

        raw_text = caller(call_prompt, model, api_key, base_url=base_url)
        data = extract_json(raw_text)

        try:
            validated = Storyboard(**data)
            return validated.model_dump()
        except Exception as e:
            last_error = str(e)
            if attempt >= max_retries:
                raise

    # Should not reach here, but just in case
    raise ValueError("Generation failed after all retries")
