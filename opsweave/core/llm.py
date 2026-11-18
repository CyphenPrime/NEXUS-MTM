import time
import os
import sys
from pathlib import Path

# Add project root to sys.path so config is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

VALID_AREAS = {"reading", "venue", "schedule", "food", "judging", "budget"}


def _get_gemini_thinking_config(types_mod, model_name: str):
    """Disable or minimise thinking for Gemini models based on SDK capability."""
    if not hasattr(types_mod, "ThinkingConfig"):
        return None
    try:
        # Gemini 2.5 uses thinking_budget=0 to disable thinking
        if "2.5" in model_name:
            return types_mod.ThinkingConfig(thinking_budget=0)
        # Gemini 3.x uses lowest thinking level
        elif "3" in model_name:
            try:
                return types_mod.ThinkingConfig(thinking_level="low")
            except Exception:
                return types_mod.ThinkingConfig(thinking_budget=0)
        else:
            return types_mod.ThinkingConfig(thinking_budget=0)
    except Exception:
        return None


def _call_gemini(model_name: str, system: str, user: str) -> tuple[str, str, int | None, int | None, int | None, int | None]:
    """Call Gemini using google-genai SDK. Returns (model_used, output_text, input_tokens, output_tokens, thinking_tokens, total_tokens)."""
    from google import genai
    from google.genai import types

    # Configure client without printing secrets
    client = genai.Client(
        api_key=config.API_KEY,
        http_options={"timeout": config.REQUEST_TIMEOUT_S * 1000}
    )

    config_kwargs = {
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "max_output_tokens": config.MAX_OUTPUT_TOKENS,
        "system_instruction": system,
    }

    thinking_cfg = _get_gemini_thinking_config(types, model_name)
    if thinking_cfg is not None:
        config_kwargs["thinking_config"] = thinking_cfg

    gen_config = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model_name,
        contents=user,
        config=gen_config,
    )

    output_text = response.text or ""
    model_used = getattr(response, "model_version", None) or model_name

    # Extract tokens strictly from provider usage metadata
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    total_tokens = None

    usage = getattr(response, "usage_metadata", None)
    if usage:
        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        total_tokens = getattr(usage, "total_token_count", None)

        # Provider-reported thinking tokens
        thinking_tokens = getattr(usage, "thinking_token_count", None)
        if thinking_tokens is None and hasattr(usage, "candidates_tokens_details"):
            details = usage.candidates_tokens_details
            if isinstance(details, list):
                for item in details:
                    if getattr(item, "modality", None) == "THINKING":
                        thinking_tokens = getattr(item, "token_count", None)
                        break
            elif details:
                thinking_tokens = getattr(details, "thinking_token_count", None)

    return model_used, output_text, input_tokens, output_tokens, thinking_tokens, total_tokens


def _call_openai(model_name: str, system: str, user: str) -> tuple[str, str, int | None, int | None, int | None, int | None]:
    """Call OpenAI or OpenAI-compatible endpoint. Returns (model_used, output_text, input_tokens, output_tokens, thinking_tokens, total_tokens)."""
    from openai import OpenAI

    base_url = config.BASE_URL if config.BASE_URL else None
    client = OpenAI(
        api_key=config.API_KEY or "none",
        base_url=base_url,
        timeout=config.REQUEST_TIMEOUT_S,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Attempt with response_format json_object first, fallback if server doesn't support it
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.0,
            max_tokens=config.MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        # Fallback if server rejects response_format
        if "response_format" in str(e).lower():
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.0,
                max_tokens=config.MAX_OUTPUT_TOKENS,
            )
        else:
            raise

    choice = response.choices[0]
    output_text = choice.message.content or ""
    model_used = response.model or model_name

    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    total_tokens = None

    usage = getattr(response, "usage", None)
    if usage:
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        details = getattr(usage, "completion_tokens_details", None)
        if details:
            thinking_tokens = getattr(details, "reasoning_tokens", None)

    return model_used, output_text, input_tokens, output_tokens, thinking_tokens, total_tokens


def call_model(area: str, system: str, user: str) -> dict:
    """
    ONE public function for calling language models.
    Validates area, handles provider abstraction, records provider-only tokens,
    and returns a standardized trace-ready dict.
    """
    if area not in VALID_AREAS:
        raise ValueError(f"Invalid area '{area}'. Must be one of: {', '.join(sorted(VALID_AREAS))}")

    exact_input = f"{system}\n\n{user}"
    start_time = time.perf_counter()

    provider = config.PROVIDER.lower()
    model_name = config.MODEL

    try:
        if provider == "gemini":
            model_used, output_text, in_tok, out_tok, th_tok, tot_tok = _call_gemini(model_name, system, user)
        elif provider == "openai":
            model_used, output_text, in_tok, out_tok, th_tok, tot_tok = _call_openai(model_name, system, user)
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER '{config.PROVIDER}'. Must be 'gemini' or 'openai'.")

        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "model": model_used,
            "area": area,
            "input": exact_input,
            "output": output_text,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "thinking_tokens": th_tok,
            "total_tokens": tot_tok,
            "status": "success",
            "error": None,
            "seconds": elapsed,
        }

    except Exception as e:
        elapsed = round(time.perf_counter() - start_time, 2)
        # Never expose API key in error message
        err_msg = str(e)
        if config.API_KEY and config.API_KEY in err_msg:
            err_msg = err_msg.replace(config.API_KEY, "[REDACTED_API_KEY]")
        return {
            "model": model_name,
            "area": area,
            "input": exact_input,
            "output": "",
            "input_tokens": None,
            "output_tokens": None,
            "thinking_tokens": None,
            "total_tokens": None,
            "status": "error",
            "error": err_msg,
            "seconds": elapsed,
        }
