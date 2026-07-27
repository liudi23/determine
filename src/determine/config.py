"""Configuration — every fixed MVP decision is a named, visible setting.

Independence constraint (MVP proposal §3): answerer.family != verifier.family,
asserted at startup. Budgets (MVP proposal §5) are config, not literals in code.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelRole(BaseModel):
    family: str          # e.g. "anthropic" | "openai" | "hf-open-weight"
    name: str            # e.g. "claude-sonnet-*", "gpt-*", "..."


class Budgets(BaseModel):
    retrieval_retries_per_claim: int = 2
    numeric_checker_iterations: int = 2   # 1 generation + 1 reflection fix
    plan_revisions: int = 1
    run_wall_clock_seconds: int = 300
    run_token_cap: int = 200_000


class KGConfig(BaseModel):
    enabled: bool = False                 # MVP: no graph (plan v2 §11)
    store_path: str = "data/kg.sqlite"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DETERMINE_", env_file=".env", extra="ignore")

    # roles — families MUST differ between answerer and verifier.
    # Model IDs confirmed available on this account (check_keys.py + models.list, 2026-07):
    #   anthropic: claude-sonnet-5 (also claude-opus-5 for final demos)
    #   openai:    gpt-5.6-luna (dev) / gpt-5.6-terra (scored eval runs)
    # Override via env, e.g. DETERMINE_VERIFIER='{"family":"openai","name":"gpt-5.6-terra"}'
    answerer: ModelRole = ModelRole(family="anthropic", name="claude-sonnet-5")
    planner: ModelRole = ModelRole(family="anthropic", name="claude-sonnet-5")
    decomposer: ModelRole = ModelRole(family="anthropic", name="claude-sonnet-5")
    verifier: ModelRole = ModelRole(family="openai", name="gpt-5.6-luna")

    budgets: Budgets = Budgets()
    kg: KGConfig = KGConfig()

    corpus_dir: str = "data/corpus"
    corpus_version: str = "hepph-dev"
    runs_dir: str = "runs"
    top_k_passages: int = 8
    verdict_tolerance_relative: float = 0.05
    dry_run: bool = True                  # stub mode: no LLM calls, deterministic outputs

    def assert_independence(self) -> None:
        if self.answerer.family == self.verifier.family:
            raise RuntimeError(
                f"independence violation: answerer and verifier share family "
                f"'{self.answerer.family}' (MVP proposal §3)"
            )

    def config_hash(self) -> str:
        payload = self.model_dump()
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]


def load_settings() -> Settings:
    s = Settings()
    s.assert_independence()
    return s
