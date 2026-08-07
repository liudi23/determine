"""LLM client layer: one interface, two vendors, aggressive disk cache.

- Vendor SDKs are imported lazily so dry-run environments never need them.
- Every completion is cached on sha256(family + model + system + user); re-runs are free.
- JSON contract helper `extract_json` tolerates markdown fences and leading prose.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
from typing import Protocol


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — sets os.environ for keys not already set."""
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


class LLM(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str: ...


class _CachedClient:
    def __init__(self, family: str, model: str, cache_dir: str = "data/llm_cache",
                 max_retries: int = 3):
        self.family, self.model = family, model
        self.cache_dir = pathlib.Path(cache_dir)
        self.max_retries = max_retries

    # -- cache --------------------------------------------------------------
    def _cache_key(self, system: str, user: str, max_tokens: int) -> pathlib.Path:
        h = hashlib.sha256(
            json.dumps([self.family, self.model, system, user, max_tokens]).encode()
        ).hexdigest()[:32]
        return self.cache_dir / f"{h}.json"

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        key = self._cache_key(system, user, max_tokens)
        if key.exists():
            return json.loads(key.read_text())["text"]
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                text = self._call(system, user, max_tokens)
                key.parent.mkdir(parents=True, exist_ok=True)
                key.write_text(json.dumps({"model": self.model, "text": text}))
                return text
            except Exception as e:  # rate limits / transient errors
                last = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts: {last}")

    def _call(self, system: str, user: str, max_tokens: int) -> str:  # pragma: no cover
        raise NotImplementedError


class AnthropicClient(_CachedClient):
    def _call(self, system: str, user: str, max_tokens: int) -> str:  # pragma: no cover
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        resp = client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class OpenAIClient(_CachedClient):
    def _call(self, system: str, user: str, max_tokens: int) -> str:  # pragma: no cover
        import openai

        client = openai.OpenAI()  # reads OPENAI_API_KEY from env
        resp = client.chat.completions.create(
            model=self.model, max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""


def make_client(family: str, model: str, cache_dir: str = "data/llm_cache") -> LLM:
    if family == "anthropic":
        return AnthropicClient(family, model, cache_dir)
    if family == "openai":
        return OpenAIClient(family, model, cache_dir)
    raise ValueError(f"unknown model family: {family}")


# ── JSON contract helper ────────────────────────────────────────────────────

def extract_json(text: str) -> dict | list:
    """Parse the first JSON object/array in an LLM response.

    Tolerates ```json fences and prose before/after. Raises ValueError if none found.
    """
    text = text.strip()
    # fenced block — tolerate a MISSING closing fence (truncated responses)
    fence = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", text, re.DOTALL)
    if fence and fence.group(1).strip():
        text = fence.group(1).strip()
    # fast path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # scan for balanced {...} / [...] candidates; return the LARGEST parseable one,
    # so a truncated outer object salvages its biggest complete substructure rather
    # than whatever tiny fragment happens to come first
    best: tuple[int, dict | list] | None = None
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start:i + 1])
                            size = i + 1 - start
                            if best is None or size > best[0]:
                                best = (size, parsed)
                        except json.JSONDecodeError:
                            pass
                        break
            start = text.find(opener, start + 1)
    if best is not None:
        return best[1]
    raise ValueError(f"no parseable JSON in LLM response: {text[:120]!r}")
