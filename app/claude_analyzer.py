import json
from google import genai
from app.config import GEMINI_API_KEY


def analyze_text(title: str, url: str, text: str) -> dict:
    if not GEMINI_API_KEY:
        return {
            "evidence_match": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "source_reliability": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "context_consistency": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "cross_verification": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "claim_clarity": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "expression_risk": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "recency": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
            "harm_risk": {"score": 50, "summary": "API 키가 없어 분석을 건너뜁니다."},
        }

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""너는 언론 기사 형식 분석 전문가야. 아래 기사를 분석해줘.

제목: {title}
URL: {url}
본문:
{text[:3000]}

중요 규칙:
- 기사에 등장하는 인물, 직책, 정책, 사건이 실제로 존재하는지 판단하지 마
- 네 학습 데이터에 없는 최신 정보라도 가짜라고 판단하지 마
- 오직 기사의 형식, 구조, 표현 방식만 평가해

각 항목 평가 기준:
- evidence_match: 기사 내 주장이 인용문·수치·날짜·출처 등 구체적 근거와 일치하는지
- source_reliability: URL 도메인이 알려진 언론사인지, 기사 형식(byline, 날짜, 출처 표기)이 정상인지
- context_consistency: 제목·본문·이미지 설명이 서로 맥락상 일치하는지, 문맥 왜곡이 없는지
- cross_verification: 본문에 다른 언론사·기관·전문가 인용이 있어 교차 확인이 가능한지
- claim_clarity: 기사의 핵심 주장이 명확하고 검증 가능한 형태로 제시되는지
- expression_risk: 낚시성 제목, 선동적 표현, 감정 유발 문구가 얼마나 많은지 (적을수록 높은 점수)
- recency: 기사에 날짜·시점이 명시되어 있고 현재 시점과 관련성이 있는지
- harm_risk: 건강·선거·금융·재난 등 사회적으로 위험한 주제를 다루는지 (위험할수록 낮은 점수)

아래 JSON 형식으로만 응답해. 다른 말은 절대 하지 마:
{{
  "overall_summary": {{
    "verdict": "신뢰 가능 / 주의 필요 / 의심 필요 / 가짜뉴스 가능성 높음 중 하나",
    "reasons": ["감점 사유 1", "감점 사유 2", "감점 사유 3"]
  }},
  "evidence_match": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "source_reliability": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "context_consistency": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "cross_verification": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "claim_clarity": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "expression_risk": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "recency": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}},
  "harm_risk": {{"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"}}
}}

score는 신뢰할수록 높은 점수 (100 = 완전 신뢰, 0 = 매우 의심)
overall_summary의 reasons는 반드시 점수가 낮은 항목(70점 미만)의 문제점만 써줘. 긍정적인 내용은 절대 쓰지 마. 70점 미만 항목이 없으면 빈 배열로 줘."""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "temperature": 0.1,
            "tools": [{"google_search": {}}],
        },
    )

    raw = response.text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)