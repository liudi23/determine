"""KGStore interface — defined now, no-op in MVP (plan v2 §11, change #4).

The pipeline only ever sees this interface; SQLite lands in Phase 2, Kùzu/Neo4j later if
justified. Keeping it here (one file, zero implementation) is what makes the KG a bolt-on
for the pipeline while the pipeline stays KG-ready.
"""

from __future__ import annotations

from typing import Any, Protocol


class KGStore(Protocol):
    def commit(self, assertions: list[dict[str, Any]]) -> None: ...
    def find_entity(self, slug_or_alias: str) -> list[dict]: ...
    def claims_for(self, entity_slug: str) -> list[dict]: ...
    def verdict_history(self, claim_id: str) -> list[dict]: ...
    def neighbors(self, node_id: str, edge_types: list[str], depth: int = 1) -> list[dict]: ...


class NoopKGStore:
    """MVP implementation: records nothing, returns nothing."""

    def commit(self, assertions: list[dict[str, Any]]) -> None:
        return None

    def find_entity(self, slug_or_alias: str) -> list[dict]:
        return []

    def claims_for(self, entity_slug: str) -> list[dict]:
        return []

    def verdict_history(self, claim_id: str) -> list[dict]:
        return []

    def neighbors(self, node_id: str, edge_types: list[str], depth: int = 1) -> list[dict]:
        return []
