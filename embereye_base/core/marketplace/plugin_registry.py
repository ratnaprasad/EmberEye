from __future__ import annotations

from .models import AnalyticDescriptor


class PluginRegistry:
    def __init__(self):
        self._descriptors: dict[str, AnalyticDescriptor] = {}

    def all(self) -> list[AnalyticDescriptor]:
        return sorted(self._descriptors.values(), key=lambda item: item.metadata.name.lower())

    def get(self, analytic_id: str) -> AnalyticDescriptor | None:
        return self._descriptors.get(analytic_id)

    def upsert(self, descriptor: AnalyticDescriptor) -> None:
        self._descriptors[descriptor.analytic_id] = descriptor

    def remove(self, analytic_id: str) -> AnalyticDescriptor | None:
        return self._descriptors.pop(analytic_id, None)

    def ids(self) -> set[str]:
        return set(self._descriptors.keys())
