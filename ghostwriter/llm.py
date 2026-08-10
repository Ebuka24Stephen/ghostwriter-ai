import os
import re
import threading
import time

from . import config

_groq_client = None
_gemini_client = None
_model_index = 0

_client_lock = threading.Lock()
_model_lock = threading.Lock()

DEFAULT_GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        with _client_lock:
            if _groq_client is None:
                from groq import Groq

                _groq_client = Groq(api_key=os.getenv(config.GROQ_API_KEY))
    return _groq_client


def get_client():
    global _gemini_client
    if config.LLM_PROVIDER == "gemini":
        if _gemini_client is None:
            with _client_lock:
                if _gemini_client is None:
                    from google import genai

                    _gemini_client = genai.Client(api_key=os.getenv(config.GEMINI_API_KEY))
        return _gemini_client
    return _get_groq_client()


def _available_models():
    raw = os.environ.get("GEMINI_MODELS", "")
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [config.GEMINI_MODEL] + [m for m in DEFAULT_GEMINI_MODELS if m != config.GEMINI_MODEL]


def _current_model():
    with _model_lock:
        models = _available_models()
        return models[_model_index % len(models)]


def _advance_model():
    global _model_index
    with _model_lock:
        _model_index += 1


def _retry_delay(message: str) -> float:
    m = re.search(r"retry in ([\d.]+)s", message, re.IGNORECASE)
    return float(m.group(1)) if m else 15.0


def _is_quota_error(e: Exception) -> bool:
    msg = str(e)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _groq_available() -> bool:
    return bool(os.getenv(config.GROQ_API_KEY))


def _gemini_generate(model: str, prompt: str, system_prompt: str, temperature: float) -> str:
    from google.genai import types

    client = get_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
        ),
    )
    return response.text.strip()


def _ask_gemini(prompt: str, system_prompt: str, temperature: float) -> str:
    last_err = None
    attempts_per_model = 3
    for _ in range(len(_available_models())):
        model = _current_model()
        for attempt in range(attempts_per_model):
            try:
                return _gemini_generate(model, prompt, system_prompt, temperature)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    last_err = e
                    delay = _retry_delay(msg)
                    if delay <= 10.0:
                        time.sleep(delay)
                        continue
                    break
                if "503" in msg or "UNAVAILABLE" in msg:
                    last_err = e
                    if attempt < attempts_per_model - 1:
                        time.sleep(3 * (attempt + 1))
                    continue
                raise
        _advance_model()
    if last_err is not None:
        raise last_err
    raise RuntimeError("No Gemini model available")


def _ask_groq(prompt: str, system_prompt: str, temperature: float) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = _get_groq_client().chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def ask(prompt: str, system_prompt: str = None, temperature: float = 0.4) -> str:
    if config.LLM_PROVIDER == "gemini":
        try:
            return _ask_gemini(prompt, system_prompt, temperature)
        except Exception as e:
            if not _is_quota_error(e):
                raise
            if _groq_available():
                try:
                    return _ask_groq(prompt, system_prompt, temperature)
                except Exception as groq_err:
                    raise RuntimeError(
                        f"Gemini API quota exhausted and Groq fallback failed: {groq_err}"
                    ) from e
            raise RuntimeError(
                "Gemini API quota exhausted and no GROQ_API_KEY is set for automatic fallback."
            ) from e
    return _ask_groq(prompt, system_prompt, temperature)
