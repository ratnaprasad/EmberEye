from __future__ import annotations

from embereye_base.core.analytics import AnalyticMetadata, AnalyticPlugin, AnalyticResult, FrameData


class Analytic(AnalyticPlugin):
    def __init__(self):
        self._config: dict[str, object] = {}

    def get_metadata(self) -> AnalyticMetadata:
        return AnalyticMetadata(
            analytic_id="sample_guard",
            name="Sample Guard",
            version="1.0.0",
            module_name="sample_guard",
            entry_class="Analytic",
            description="Reference analytic package structure for Phase 2 marketplace work.",
            execution_hints={"trigger": "every_n_frames", "value": 5, "policy": "sequential"},
            required_license="sample_guard",
        )

    def configure(self, config: dict[str, object]) -> None:
        self._config = dict(config)

    def process_frame(self, frame: FrameData, context: dict[str, object] | None = None) -> AnalyticResult:
        return AnalyticResult(
            analytic_id="sample_guard",
            success=True,
            payload={
                "frame_id": frame.frame_id,
                "source_id": frame.source_id,
                "configured": bool(self._config),
            },
            metadata={"context_keys": sorted((context or {}).keys())},
        )
