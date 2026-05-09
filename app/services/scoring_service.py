"""Scoring stage for deterministic trust-score computation."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import AnalysisOutput, ScoringOutput, derive_score_band


class ScoringService(ABC):
    """Contract for converting analysis output into weighted score payload."""

    @abstractmethod
    def score(self, analysis_output: AnalysisOutput) -> ScoringOutput:
        """Compute weighted score from analysis criteria."""


class DeterministicScoringService(ScoringService):
    """Deterministic weighted scoring implementation."""

    WEIGHTS: dict[str, int] = {
        "source_reliability": 25,
        "claim_consistency": 25,
        "evidence_quality": 20,
        "expression_risk": 15,
        "multimodal_risk": 15,
    }

    CRITERION_LABELS: dict[str, str] = {
        "source_reliability": "출처 신뢰도",
        "claim_consistency": "주장 일관성",
        "evidence_quality": "근거 품질",
        "expression_risk": "선동 표현 위험도",
        "multimodal_risk": "멀티모달 조작 위험도",
    }

    def score(self, analysis_output: AnalysisOutput) -> ScoringOutput:
        criteria = {
            "source_reliability": analysis_output.source_reliability.score,
            "claim_consistency": analysis_output.claim_consistency.score,
            "evidence_quality": analysis_output.evidence_quality.score,
            "expression_risk": analysis_output.expression_risk.score,
            "multimodal_risk": analysis_output.multimodal_risk.score,
        }

        weighted_sum = 0
        total_weight = 0
        rationale: list[str] = []
        for key, weight in self.WEIGHTS.items():
            weighted_sum += criteria[key] * weight
            total_weight += weight
            rationale.append(
                f"{self.CRITERION_LABELS[key]}: {criteria[key]}점 ({weight}%)"
            )

        score = round(weighted_sum / total_weight)
        if score > 100:
            score = 100

        score_band = derive_score_band(score)

        return ScoringOutput(
            analysis_id=analysis_output.analysis_id,
            score=score,
            score_band=score_band,
            criteria_breakdown=criteria,
            rationale=rationale,
        )


__all__ = ["ScoringService", "DeterministicScoringService"]

