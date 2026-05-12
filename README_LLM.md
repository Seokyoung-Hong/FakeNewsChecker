# LLM 연동 모듈 (민지원)

REST API, CLI 형태 상관 없이 링크를 AI에게 분석시키는 모듈입니다.

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `app/gemini_analyzer.py` | Gemini API로 기사 텍스트 분석 |
| `app/hive_analyzer.py` | Hive Moderation API로 이미지 AI 생성·딥페이크 탐지 |
| `app/scoring.py` | 항목별 가중치로 최종 신뢰도 점수 계산 |
| `app/config.py` | 환경변수 로드 |

---

## 필요한 API 키

`.env` 파일에 아래 키 추가 필요:

```
GEMINI_API_KEY=여기에입력
HIVE_API_KEY=여기에입력
```

- **Gemini API** 발급: https://aistudio.google.com/app/apikey
- **Hive API** 발급: https://portal.thehive.ai/signup (Secret Key 사용)

---

## 사용법

```python
from app.gemini_analyzer import analyze_text
from app.hive_analyzer import analyze_images
from app.scoring import calculate_score, get_label

# 1. 텍스트 분석 (Gemini)
text_result = analyze_text(
    title="기사 제목",
    url="https://example.com/news",
    text="크롤링된 본문 텍스트",
)

# 2. 이미지 분석 (Hive)
image_result = analyze_images(["https://example.com/image.jpg"])

# 3. 결합 + 점수 계산
full_result = {**text_result, "multimodal_risk": image_result}
score = calculate_score(full_result)
label = get_label(score)
```

---

## 분석 항목 및 가중치

| 항목 | 가중치 | 설명 |
|---|---|---|
| 근거 일치성 | 25점 | 주장과 근거 일치 여부 |
| 이미지·영상 진위성 | 20점 | AI 생성·딥페이크 탐지 |
| 출처 신뢰성 | 15점 | 언론사·도메인 신뢰도 |
| 맥락 정합성 | 15점 | 문맥 왜곡·재사용 여부 |
| 교차 검증 | 10점 | 다른 출처 확인 가능 여부 |
| 주장 명확성 | 5점 | 검증 가능한 주장인지 |
| 확산·조작 패턴 | 5점 | 낚시성·선동성 여부 |
| 최신성 | 3점 | 정보 유효성 |
| 피해 위험도 | 2점 | 사회적 위험성 |

---

## 결과 형식

```json
{
  "overall_summary": {
    "verdict": "신뢰 가능",
    "reasons": ["감점 사유 1", "감점 사유 2"]
  },
  "evidence_match": {"score": 90, "summary": "설명"},
  "source_reliability": {"score": 95, "summary": "설명"},
  "multimodal_risk": {"score": 100, "summary": "이미지 조작 가능성은 낮습니다."}
}
```
