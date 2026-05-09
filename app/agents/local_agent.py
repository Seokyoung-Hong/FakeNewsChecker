"""Deterministic offline agent implementation for all local analysis stages."""

# pyright: reportMissingImports=false, reportImplicitOverride=false

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from app.agents.base import AnalysisAgent
from app.schemas import AnalysisCriterionResult, CrawlerOutput


def _stable_int(seed: str, floor: int = 0, ceil: int = 100) -> int:
    """Return a deterministic integer in a fixed range from a deterministic key."""

    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:10], 16)
    return floor + (value % (ceil - floor + 1))


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


class LocalAgent(AnalysisAgent):
    """Deterministic pure-Python analysis agent.

    No network requests or external dependencies are used here.
    """

    name: str = "local-agent"

    def analyze(self, crawler_output: CrawlerOutput, criterion: str) -> AnalysisCriterionResult:
        method_map = {
            "source_reliability": self._analyze_source_reliability,
            "claim_consistency": self._analyze_claim_consistency,
            "evidence_quality": self._analyze_evidence_quality,
            "expression_risk": self._analyze_expression_risk,
            "multimodal_risk": self._analyze_multimodal_risk,
        }
        handler = method_map.get(criterion)
        if handler is None:
            raise ValueError(f"Unsupported criterion: {criterion}")

        return handler(crawler_output)

    def _analyze_source_reliability(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        host = urlparse(str(payload.url)).hostname or ""
        host = host.lower()
        if any(item in host for item in ("wikipedia.org", "apnews.com", "reuters.com")):
            base_score = 86
        elif any(item in host for item in ("nytimes.com", "bbc.com", "cnn.com", "korea.kr", "yonhap.co.kr")):
            base_score = 80
        elif any(item in host for item in ("blog", "community", "forum", "example")):
            base_score = 56
        else:
            base_score = 68

        adjustment = _stable_int(f"{payload.analysis_id}:source", -8, 8)
        score = _clamp(base_score + adjustment, 30, 95)

        risk = "low" if score >= 78 else "medium" if score >= 60 else "high"
        return AnalysisCriterionResult(
            score=score,
            summary=f"출처 신뢰도는 도메인 패턴과 정적 신호를 기반으로 {score}점으로 계산됩니다.",
            risk=risk,
        )

    def _analyze_claim_consistency(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        content = payload.content
        words = content.split()
        support_terms = [
            "근거",
            "출처",
            "자료",
            "통계",
            "연구",
            "보고서",
            "증거",
            "공식",
        ]
        hit_count = sum(1 for term in support_terms if term in content)
        length_score = _clamp(len(words), 30, 220)
        base = 50 + (length_score // 4) + (hit_count * 6)
        adjustment = _stable_int(f"{payload.analysis_id}:claim", -10, 10)
        score = _clamp(base + adjustment, 25, 95)
        risk = "low" if score >= 75 else "medium" if score >= 55 else "high"

        return AnalysisCriterionResult(
            score=score,
            summary=f"핵심 주장의 근거 신호가 {hit_count}건 확인되어 {score}점입니다.",
            risk=risk,
        )

    def _analyze_evidence_quality(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        content_len = len(payload.content)
        has_metadata = 1 if payload.metadata else 0
        word_bonus = content_len // 20
        image_bonus = len(payload.images) * 4
        stable_adjust = _stable_int(f"{payload.analysis_id}:evidence", -6, 6)

        base_score = 42 + has_metadata * 12 + _clamp(word_bonus, 0, 22) + image_bonus
        score = _clamp(base_score + stable_adjust, 25, 95)
        risk = "low" if score >= 70 else "medium" if score >= 55 else "high"

        return AnalysisCriterionResult(
            score=score,
            summary=f"본문 길이와 부가 메타데이터를 기반으로 근거 품질 점수를 산출했습니다.",
            risk=risk,
        )

    def _analyze_expression_risk(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        content = payload.content
        trigger_terms = [
            "충격",
            "망신",
            "사기",
            "완전",
            "단번",
            "반드시",
            "무조건",
            "절대",
            "전부",
            "공포",
        ]
        trigger_count = sum(1 for term in trigger_terms if term in content)
        penalty = trigger_count * 8
        stable_adjust = _stable_int(f"{payload.analysis_id}:expression", -8, 8)

        base_score = 84 - _clamp(penalty, 4, 40) + stable_adjust
        score = _clamp(base_score, 20, 95)
        risk = "low" if score >= 80 else "medium" if score >= 55 else "high"

        return AnalysisCriterionResult(
            score=score,
            summary=f"감정·선동 표현 지표를 반영해 {score}점으로 평가했습니다.",
            risk=risk,
        )

    def _analyze_multimodal_risk(self, payload: CrawlerOutput) -> AnalysisCriterionResult:
        image_count = len(payload.images)
        if image_count == 0:
            base_score = 74
        elif image_count == 1:
            base_score = 81
        elif image_count == 2:
            base_score = 87
        else:
            base_score = 71

        stable_adjust = _stable_int(f"{payload.analysis_id}:multimodal", -6, 6)
        score = _clamp(base_score + stable_adjust, 22, 95)
        risk = "low" if score >= 80 else "medium" if score >= 60 else "high"

        return AnalysisCriterionResult(
            score=score,
            summary=f"수집된 이미지 수({image_count}개) 기준으로 조작 가능성 점수를 산정했습니다.",
            risk=risk,
        )


__all__ = ["LocalAgent"]

