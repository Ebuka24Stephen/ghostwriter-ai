import os
import re
import threading
import time

from . import config

_groq_client = None
_gemini_clients: dict[str, object] = {}
_model_index = 0

_client_lock = threading.Lock()
_model_lock = threading.Lock()

DEFAULT_GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
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
    keys = _api_keys()
    if config.LLM_PROVIDER == "gemini" and keys:
        return _get_gemini_client(keys[0])
    return _get_groq_client()


def _api_keys():
    names = ("GEMINI_API_KEY", "GEMINI_API_KEY2")
    seen = []
    for name in names:
        value = os.getenv(name, "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _get_gemini_client(api_key: str):
    if api_key not in _gemini_clients:
        with _client_lock:
            if api_key not in _gemini_clients:
                from google import genai

                _gemini_clients[api_key] = genai.Client(api_key=api_key)
    return _gemini_clients[api_key]


def _available_models():
    raw = os.environ.get("GEMINI_MODELS", "")
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [config.GEMINI_MODEL] + [m for m in DEFAULT_GEMINI_MODELS if m != config.GEMINI_MODEL]


def _rotation_pairs():
    keys = _api_keys()
    if not keys:
        return []
    return [(key, model) for model in _available_models() for key in keys]


def _current_pair():
    with _model_lock:
        pairs = _rotation_pairs()
        return pairs[_model_index % len(pairs)] if pairs else (None, None)


def _advance_model():
    global _model_index
    with _model_lock:
        _model_index += 1


def _retry_delay(message: str) -> float:
    m = re.search(r"(?:retry|try again) in ([\d.]+)s", message, re.IGNORECASE)
    return float(m.group(1)) if m else 15.0


def _is_quota_error(e: Exception) -> bool:
    msg = str(e)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _is_model_unavailable(e: Exception) -> bool:
    msg = str(e)
    return "404" in msg or "NOT_FOUND" in msg


def _is_overloaded(e: Exception) -> bool:
    msg = str(e)
    return "503" in msg or "UNAVAILABLE" in msg


def _is_fallback_error(e: Exception) -> bool:
    return _is_quota_error(e) or _is_model_unavailable(e) or _is_overloaded(e)


def _groq_available() -> bool:
    return bool(os.getenv(config.GROQ_API_KEY))


def _gemini_generate(api_key: str, model: str, prompt: str, system_prompt: str, temperature: float) -> str:
    from google.genai import types

    client = _get_gemini_client(api_key)
    chat = client.chats.create(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
        ),
    )
    response = chat.send_message(prompt)
    return response.text.strip()


def _ask_gemini(prompt: str, system_prompt: str, temperature: float) -> str:
    last_err = None
    attempts_per_pair = 3
    budget = 55.0
    start = time.monotonic()

    def _remaining() -> float:
        return budget - (time.monotonic() - start)

    for _ in range(len(_rotation_pairs())):
        if _remaining() <= 0:
            break
        api_key, model = _current_pair()
        if not api_key:
            break
        for attempt in range(attempts_per_pair):
            if _remaining() <= 0:
                break
            try:
                return _gemini_generate(api_key, model, prompt, system_prompt, temperature)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    last_err = e
                    if "quota" in msg.lower() and "billing" in msg.lower():
                        break
                    delay = min(_retry_delay(msg), 10.0)
                    if 0 < delay < _remaining():
                        time.sleep(delay)
                        continue
                    break
                if "503" in msg or "UNAVAILABLE" in msg:
                    last_err = e
                    if attempt == 0:
                        time.sleep(min(2.0, max(_remaining(), 0)))
                        continue
                    break
                if "404" in msg or "NOT_FOUND" in msg:
                    last_err = e
                    break
                raise
        _advance_model()
    if last_err is not None:
        raise last_err
    raise RuntimeError("No Gemini key/model available")


def _ask_groq(prompt: str, system_prompt: str, temperature: float) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_err = None
    for attempt in range(3):
        try:
            response = _get_groq_client().chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            msg = str(e)
            if "429" in msg or "RATE_LIMIT" in msg or "rate limit" in msg.lower():
                delay = min(_retry_delay(msg), 10.0)
                if attempt < 2 and delay <= 10.0:
                    time.sleep(delay)
                    continue
            raise
    raise last_err


def ask(prompt: str, system_prompt: str = None, temperature: float = 0.4) -> str:
    if config.LLM_PROVIDER == "gemini":
        try:
            return _ask_gemini(prompt, system_prompt, temperature)
        except Exception as e:
            if not _is_fallback_error(e):
                raise
            if _groq_available():
                try:
                    return _ask_groq(prompt, system_prompt, temperature)
                except Exception as groq_err:
                    raise RuntimeError(
                        f"Gemini API unavailable and Groq fallback failed: {groq_err}"
                    ) from e
            raise RuntimeError(
                "Gemini API unavailable and no GROQ_API_KEY is set for automatic fallback."
            ) from e
    return _ask_groq(prompt, system_prompt, temperature)
