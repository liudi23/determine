"""Verify both API keys authenticate — zero-cost (uses the free list-models endpoints).

Run from the project folder with the venv active:
    python scripts/check_keys.py
"""

from __future__ import annotations

import pathlib
import re
import sys


def load_env(path: str = ".env") -> dict[str, str]:
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit("FAIL: .env not found — run from the determine-mvp folder")
    env: dict[str, str] = {}
    for line in p.read_text().splitlines():
        m = re.match(r"^\s*([A-Z_]+)\s*=\s*(.*)\s*$", line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def main() -> None:
    env = load_env()
    ok = True

    # Anthropic
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY", ""))
        models = [m.id for m in client.models.list(limit=5).data]
        print(f"Anthropic  OK — authenticated; example models: {models[:3]}")
    except Exception as e:
        ok = False
        print(f"Anthropic  FAIL — {type(e).__name__}: {e}")

    # OpenAI
    try:
        import openai
        client = openai.OpenAI(api_key=env.get("OPENAI_API_KEY", ""))
        models = [m.id for m in client.models.list().data[:5]]
        print(f"OpenAI     OK — authenticated; example models: {models[:3]}")
    except Exception as e:
        ok = False
        print(f"OpenAI     FAIL — {type(e).__name__}: {e}")

    if ok:
        print("\nBoth keys authenticate. Note the exact model IDs above — "
              "we pin the config defaults to real IDs from these lists.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
