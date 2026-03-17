"""
LLM integration for automated storyboard generation.

Supports OpenAI, Anthropic, Google Gemini, ZhipuAI, Ollama, and any
OpenAI-compatible endpoint. Lazy SDK imports mean only the used
provider's package needs to be installed.

Structured-output mode is used where supported, eliminating regex
JSON extraction and parse retries for those providers. [web:128][web:133]

Usage:
    from manimator.llm import generate_storyboard, list_providers

    result = generate_storyboard(
        topic="How CRISPR works",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-...",
    )
    print(result.storyboard)   # validated dict
    print(result.usage)        # {"prompt_tokens": …, "total_tokens": …}
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from manimator.schema import Storyboard
from manimator.topic_templates import get_storyboard_prompt

log = logging.getLogger(__name__)


# ── Provider Registry ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderInfo:
    models:            list[str]
    default:           str
    env_key:           str
    base_url:          str  = ""
    # Does this provider support native JSON-schema structured outputs?
    structured_output: bool = False
    # Approximate context window in tokens (for prompt truncation guard)
    context_window:    int  = 8_192


PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo(
        models=["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        default="gpt-4o-mini",
        env_key="OPENAI_API_KEY",
        structured_output=True,    # json_schema response_format [web:128]
        context_window=128_000,
    ),
    "anthropic": ProviderInfo(
        models=[
            "claude-opus-4-6", "claude-sonnet-4-5",
            "claude-sonnet-4-20250514", "claude-haiku-4-5-20251001",
        ],
        default="claude-sonnet-4-20250514",
        env_key="ANTHROPIC_API_KEY",
        structured_output=True,    # output_config.format [web:133][web:136]
        context_window=200_000,
    ),
    "google": ProviderInfo(
        models=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"],
        default="gemini-2.5-flash",
        env_key="GOOGLE_API_KEY",
        structured_output=False,
        context_window=1_000_000,
    ),
    "zhipuai": ProviderInfo(
        models=["glm-5", "glm-5-turbo", "glm-4.7", "glm-4.7-FlashX", "glm-4.7-Flash"],
        default="glm-5",
        env_key="ZHIPUAI_API_KEY",
        base_url="https://api.z.ai/api/paas/v4/",
        structured_output=False,
        context_window=128_000,
    ),
    "ollama": ProviderInfo(
        models=["llama3.2", "llama3.1", "mistral", "qwen2.5", "gemma3", "phi4"],
        default="llama3.2",
        env_key="",
        base_url="http://localhost:11434/v1",
        structured_output=False,
        context_window=32_768,
    ),
    "openai_compatible": ProviderInfo(
        models=[],
        default="",
        env_key="OPENAI_API_KEY",
        structured_output=False,
        context_window=32_768,
    ),
}


# ── Result type ────────────────────────────────────────────────────────────

@dataclass
class GenerationResult:
    storyboard:  dict
    provider:    str
    model:       str
    usage:       dict[str, int] = field(default_factory=dict)
    retries:     int = 0
    used_native_schema: bool = False


# ── Backoff utility ────────────────────────────────────────────────────────

def _backoff_delay(attempt: int, base: float = 1.5, cap: float = 60.0) -> float:
    """
    Exponential backoff with full jitter: delay ∈ [0, min(cap, base^attempt)].
    Jitter prevents thundering-herd on concurrent retries. [web:134][web:137]
    """
    ceiling = min(cap, base ** attempt)
    return random.uniform(0, ceiling)


def _is_rate_limit(exc: Exception) -> bool:
    """Detect 429 / rate-limit errors across provider SDK types."""
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
        or "too many requests" in msg
        or (hasattr(exc, "status_code") and getattr(exc, "status_code") == 429)
    )


def _retry_after(exc: Exception) -> float | None:
    """Extract Retry-After header value if the SDK exposes it."""
    for attr in ("response", "headers"):
        obj = getattr(exc, attr, None)
        if obj is None:
            continue
        headers = getattr(obj, "headers", None) or (obj if isinstance(obj, dict) else None)
        if headers and "retry-after" in (headers or {}):
            try:
                return float(headers["retry-after"])
            except (TypeError, ValueError):
                pass
    return None


# ── JSON extraction (fallback for non-structured-output providers) ─────────

def extract_json(text: str) -> dict:
    """
    Extract a JSON object from raw LLM text.
    Handles markdown fences, leading prose, and malformed wrappers.
    Raises ValueError if no valid JSON object is found.
    """
    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Brace-counting extraction for JSON embedded in prose
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    depth, in_string, escape_next = 0, False, False
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
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Found JSON-like block but failed to parse: {e}"
                    ) from e

    raise ValueError("No complete JSON object found in LLM response")


# ── Schema export for structured-output providers ─────────────────────────

def _pydantic_json_schema() -> dict:
    """
    Export the Storyboard Pydantic model as a JSON Schema dict.
    Used by OpenAI json_schema and Anthropic output_config modes.
    """
    schema = Storyboard.model_json_schema()
    # OpenAI requires additionalProperties: false at every level [web:128]
    def _patch(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" not in node:
                node["additionalProperties"] = False
            for v in node.values():
                _patch(v)
        elif isinstance(node, list):
            for v in node:
                _patch(v)
    _patch(schema)
    return schema


# ── Provider call functions ────────────────────────────────────────────────

def _call_openai(
    prompt: str, model: str, api_key: str,
    use_structured: bool = True, **_,
) -> tuple[str | dict, dict]:
    """
    OpenAI call. Uses json_schema Structured Outputs when `use_structured=True`. [web:128]
    Returns (raw_text_or_parsed_dict, usage_dict).
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    system = (
        "You are a scientific video storyboard generator. "
        "Output ONLY valid JSON matching the requested schema."
    )

    if use_structured:
        schema = _pydantic_json_schema()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "storyboard",
                    "schema": schema,
                    "strict": True,
                },
            },
            temperature=0.7,
            max_tokens=8192,
        )
        content = response.choices[0].message.content
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = content        # fall through to extract_json
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=8192,
        )
        parsed = response.choices[0].message.content

    usage = {}
    if hasattr(response, "usage") and response.usage:
        usage = {
            "prompt_tokens":     response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens":      response.usage.total_tokens,
        }
    return parsed, usage


def _call_anthropic(
    prompt: str, model: str, api_key: str,
    use_structured: bool = True, **_,
) -> tuple[str | dict, dict]:
    """
    Anthropic call. Uses output_config structured outputs when supported. [web:133][web:136]
    Falls back to tool-use JSON extraction for older models.
    """
    from anthropic import Anthropic

    client   = Anthropic(api_key=api_key)
    system   = (
        "You are a scientific video storyboard generator. "
        "Output ONLY valid JSON matching the requested schema."
    )
    usage    = {}
    parsed: str | dict

    if use_structured:
        schema = _pydantic_json_schema()
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                # Structured outputs public beta header [web:142]
                extra_headers={"anthropic-beta": "structured-outputs-2025-11-13"},
                output_config={                          # type: ignore[arg-type]
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    }
                },
            )
            parsed = json.loads(response.content[0].text)
        except Exception as exc:
            log.warning(
                "Anthropic structured output failed (%s); falling back to text", exc
            )
            # Graceful fallback: plain text + extract_json
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = response.content[0].text
    else:
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = response.content[0].text

    if hasattr(response, "usage") and response.usage:
        usage = {
            "input_tokens":  response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens":  (
                response.usage.input_tokens + response.usage.output_tokens
            ),
        }
    return parsed, usage


def _call_google(
    prompt: str, model: str, api_key: str, **_,
) -> tuple[str, dict]:
    """Google Gemini call via google-genai SDK."""
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=(
            "You are a scientific video storyboard generator. "
            "Output ONLY valid JSON matching the requested schema.\n\n"
            + prompt
        ),
    )
    usage: dict = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        m = response.usage_metadata
        usage = {
            "prompt_tokens":     getattr(m, "prompt_token_count", 0),
            "completion_tokens": getattr(m, "candidates_token_count", 0),
            "total_tokens":      getattr(m, "total_token_count", 0),
        }
    return response.text, usage


def _call_openai_compat(
    prompt: str, model: str, api_key: str,
    base_url: str = "", temperature: float = 0.7,
    json_mode: bool = True, **_,
) -> tuple[str, dict]:
    """
    Generic OpenAI-compatible endpoint (ZhipuAI, Groq, Together, Ollama, etc.).
    Attempts json_object response_format; falls back gracefully.
    """
    from openai import OpenAI

    if not base_url:
        raise ValueError("base_url is required for this provider")
    if not model:
        raise ValueError("model is required for this provider")

    timeout = 300 if "localhost" in base_url or "ollama" in base_url else 60
    client = OpenAI(api_key=api_key or "none", base_url=base_url, timeout=timeout)

    system = (
        "You are a JSON generator. Output ONLY a raw JSON object. "
        "No markdown, no fences, no prose. Start with { and end with }."
    )
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        temperature=temperature,
        max_tokens=8192,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        if json_mode:
            # Some older models don't support response_format — retry without
            kwargs.pop("response_format", None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise

    usage: dict = {}
    if hasattr(response, "usage") and response.usage:
        u = response.usage
        usage = {
            "prompt_tokens":     getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens":      getattr(u, "total_tokens", 0),
        }
    return response.choices[0].message.content, usage


# Dispatch table — each value is (callable, uses_structured_output_flag)
_CALLERS: dict[str, Callable] = {
    "openai":            _call_openai,
    "anthropic":         _call_anthropic,
    "google":            _call_google,
    "zhipuai":           lambda *a, **kw: _call_openai_compat(
                             *a, base_url="https://api.z.ai/api/paas/v4/", **kw),
    "ollama":            lambda *a, **kw: _call_openai_compat(
                             *a, base_url=kw.pop("base_url", "http://localhost:11434/v1"),
                             temperature=0.2, **kw),
    "openai_compatible": _call_openai_compat,
}


# ── Public API ─────────────────────────────────────────────────────────────

def list_providers() -> dict[str, dict]:
    """Return provider metadata dict keyed by provider name."""
    return {
        name: {
            "models":            info.models,
            "default":           info.default,
            "structured_output": info.structured_output,
            "context_window":    info.context_window,
        }
        for name, info in PROVIDERS.items()
    }


def generate_storyboard(
    topic:          str,
    provider:       str,
    model:          str | None    = None,
    api_key:        str | None    = None,
    domain:         str | None    = None,
    structure:      str           = "explainer",
    format_type:    str           = "presentation",
    theme:          str           = "wong",
    base_url:       str           = "",
    max_retries:    int           = 2,
    on_token_usage: Callable[[dict], None] | None = None,
) -> GenerationResult:
    """
    Generate a validated storyboard from a topic using an LLM.

    Uses native structured-output modes for OpenAI and Anthropic to
    guarantee schema conformance without regex extraction. [web:128][web:133]
    Falls back to extract_json for other providers.

    Args:
        topic:          The video topic, e.g. "How CRISPR works".
        provider:       Provider key — see list_providers().
        model:          Model name; uses provider default if omitted.
        api_key:        API key; reads env var if omitted.
        domain:         Optional domain template key.
        structure:      Story structure key (default: "explainer").
        format_type:    Video format (default: "presentation").
        theme:          Color theme (default: "wong").
        base_url:       Required for openai_compatible / custom endpoints.
        max_retries:    Max retries on rate-limit or validation failure.
        on_token_usage: Optional callback receiving usage dict per attempt.

    Returns:
        GenerationResult with .storyboard (dict), .usage, .retries.

    Raises:
        ValueError:              Unknown provider / missing key / JSON failure.
        pydantic.ValidationError: Schema mismatch after all retries exhausted.
    """
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Available: {list(PROVIDERS.keys())}"
        )

    info = PROVIDERS[provider]

    # ── API key resolution ────────────────────────────────────────────
    if not api_key and info.env_key:
        api_key = os.environ.get(info.env_key, "")
    if not api_key and info.env_key:
        raise ValueError(
            f"No API key for '{provider}'. "
            f"Set the {info.env_key} environment variable or pass api_key=."
        )
    api_key = api_key or ""

    # ── Base URL / model defaults ─────────────────────────────────────
    if not base_url and info.base_url:
        base_url = info.base_url
    if not model:
        model = info.default
    if not model:
        raise ValueError(f"No default model for '{provider}'. Pass model=.")

    # ── Prompt construction ───────────────────────────────────────────
    base_prompt = get_storyboard_prompt(
        topic=topic,
        structure=structure,
        domain=domain,
        format_type=format_type,
        theme=theme,
    )

    use_native = info.structured_output
    caller     = _CALLERS[provider]
    last_error: str | None = None
    cumulative_usage: dict[str, int] = {}

    for attempt in range(max_retries + 1):

        # Exponential backoff with jitter [web:134][web:137]
        if attempt > 0:
            delay = _backoff_delay(attempt)
            log.warning(
                "Retry %d/%d for provider=%s model=%s (%.1fs delay)",
                attempt, max_retries, provider, model, delay,
            )
            time.sleep(delay)

        # Inject previous error feedback into the prompt on retries
        prompt = base_prompt
        if attempt > 0 and last_error:
            prompt += (
                "\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
                f"Validation error: {last_error}\n"
                "Please fix the JSON and output ONLY the corrected JSON object."
            )

        # ── Call provider ─────────────────────────────────────────────
        try:
            raw, usage = caller(
                prompt, model, api_key,
                base_url=base_url,
                use_structured=use_native,
            )
        except Exception as exc:
            if _is_rate_limit(exc):
                server_wait = _retry_after(exc)
                if server_wait:
                    log.warning("Rate-limited; server says wait %.0fs", server_wait)
                    time.sleep(server_wait)
                last_error = f"Rate limit: {exc}"
                if attempt >= max_retries:
                    raise
                continue
            raise

        # Accumulate usage across retries
        for k, v in usage.items():
            cumulative_usage[k] = cumulative_usage.get(k, 0) + v
        if on_token_usage:
            on_token_usage(usage)

        # ── Parse raw output ──────────────────────────────────────────
        if isinstance(raw, dict):
            # Structured output already parsed [web:128][web:133]
            data = raw
        else:
            try:
                data = extract_json(raw)
            except ValueError as exc:
                last_error = str(exc)
                log.warning("JSON extraction failed (attempt %d): %s", attempt, exc)
                if attempt >= max_retries:
                    raise
                continue

        # ── Schema validation ─────────────────────────────────────────
        try:
            validated = Storyboard(**data)
            return GenerationResult(
                storyboard=validated.model_dump(),
                provider=provider,
                model=model,
                usage=cumulative_usage,
                retries=attempt,
                used_native_schema=use_native and isinstance(raw, dict),
            )
        except Exception as exc:
            last_error = str(exc)
            log.warning("Storyboard validation failed (attempt %d): %s", attempt, exc)
            # On validation failure, fall back to text mode for next attempt
            # so the model can correct its output freely
            use_native = False
            if attempt >= max_retries:
                raise

    raise ValueError("Generation failed after all retries")


# ── Async thin wrapper ─────────────────────────────────────────────────────

async def generate_storyboard_async(
    topic:       str,
    provider:    str,
    model:       str | None = None,
    api_key:     str | None = None,
    **kwargs,
) -> GenerationResult:
    """
    Async wrapper over generate_storyboard.
    Runs the blocking call in the default executor so it doesn't
    block the event loop. Suitable for FastAPI / async pipelines.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: generate_storyboard(
            topic=topic, provider=provider,
            model=model, api_key=api_key,
            **kwargs,
        ),
    )

