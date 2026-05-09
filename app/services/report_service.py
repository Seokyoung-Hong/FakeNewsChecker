"""Report generation stage for user-facing result payload."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import AnalysisOutput, ReportDetail, ReportOutput, ScoringOutput


class ReportService(ABC):
    """Contract for transforming internal analysis/scoring into final report."""

    @abstractmethod
    def build_report(
        self,
        analysis_output: AnalysisOutput,
        scoring_output: ScoringOutput,
    ) -> ReportOutput:
        """Create report details from internal analysis and scoring DTOs."""


class DeterministicReportService(ReportService):
    """Deterministic report formatter used in the stub pipeline."""

    _DETAIL_ORDER: tuple[tuple[str, str], ...] = (
        ("source_reliability", "출처 신뢰도"),
        ("claim_consistency", "주장 일관성"),
        ("evidence_quality", "근거 품질"),
        ("expression_risk", "선동 표현 위험도"),
        ("multimodal_risk", "멀티모달 조작 위험도"),
    )

    def build_report(self, analysis_output: AnalysisOutput, scoring_output: ScoringOutput) -> ReportOutput:
        details = self._build_details(analysis_output)
        summary = self._build_summary(analysis_output, scoring_output)
        recommendation = self._build_recommendation(scoring_output.score)

        return ReportOutput(
            analysis_id=scoring_output.analysis_id,
            summary=summary,
            details=details,
            recommendation=recommendation,
        )

    def _build_details(self, analysis_output: AnalysisOutput) -> list[ReportDetail]:
        criterion_map = {
            "source_reliability": analysis_output.source_reliability,
            "claim_consistency": analysis_output.claim_consistency,
            "evidence_quality": analysis_output.evidence_quality,
            "expression_risk": analysis_output.expression_risk,
            "multimodal_risk": analysis_output.multimodal_risk,
        }

        details: list[ReportDetail] = []
        for criterion_key, label in self._DETAIL_ORDER:
            result = criterion_map[criterion_key]
            details.append(
                ReportDetail(
                    key=criterion_key,
                    label=label,
                    score=result.score,
                    summary=result.summary,
                    risk=result.risk,
                )
            )

        return details

    def _build_summary(self, analysis_output: AnalysisOutput, scoring_output: ScoringOutput) -> str:
        return (
            f"총점은 {scoring_output.score}점이며 판정은 '{scoring_output.score_band}'입니다. "
            f"{analysis_output.overall_summary}"
        )

    def _build_recommendation(self, score: int) -> str:
        if score >= 80:
            return "추가 확인이 필요하지 않은 수준으로, 현재는 신뢰 가능한 편입니다."
        if score >= 60:
            return "일부 주장에 대한 추가 검증이 권장되며, 핵심 출처를 함께 확인하세요."
        if score >= 40:
            return "신뢰도가 낮으므로 출처·반대 의견·공식 자료를 함께 확인하세요."
        return "가짜뉴스 가능성이 높으므로 재확인 없이 공유하지 마십시오."


__all__ = ["ReportService", "DeterministicReportService"]

