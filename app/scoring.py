WEIGHTS = {
    "evidence_match": 25,      # 근거 일치성
    "multimodal_risk": 20,     # 이미지·영상 진위성
    "source_reliability": 15,  # 출처 신뢰성
    "context_consistency": 15, # 맥락 정합성
    "cross_verification": 10,  # 교차 검증
    "claim_clarity": 5,        # 주장 명확성
    "expression_risk": 5,      # 확산·조작 패턴
    "recency": 3,              # 최신성
    "harm_risk": 2,            # 피해 위험도
}


def calculate_score(analysis: dict[str, dict[str, object]]) -> int:
    total = 0
    for key, weight in WEIGHTS.items():
        item_score_raw = analysis.get(key, {}).get("score", 50)
        if isinstance(item_score_raw, bool) or not isinstance(item_score_raw, (int, float)):
            item_score = 50
        else:
            item_score = float(item_score_raw)
        total += item_score * (weight / 100)
    return round(total)


def get_label(score: int) -> str:
    if score >= 80:
        return "신뢰 가능"
    elif score >= 60:
        return "주의 필요"
    elif score >= 40:
        return "의심 필요"
    else:
        return "가짜뉴스 가능성 높음"
