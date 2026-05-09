# AI 기반 가짜뉴스 URL 검증 서비스 기술 명세서

## 1. 프로젝트 개요

본 서비스는 사용자가 입력한 뉴스 기사, SNS 게시글, 블로그 등의 URL을 기반으로 콘텐츠를 수집하고, AI 기반 분석을 통해 해당 정보의 신뢰도를 검증하는 웹 서비스입니다.

서비스는 단순히 “진짜/가짜”를 단정하지 않고, 출처 신뢰도·본문 논리성·근거 존재 여부·선동 표현·이미지 조작 가능성 등을 종합 분석하여 100점 기준의 신뢰도 리포트를 제공합니다.

프로토타입 단계에서는 실제 사용 가능한 수준의 UI와 핵심 분석 흐름 구현에 집중하며, 로그인·회원가입·관리 기능 등 부가 기능은 제외합니다.

---

# 2. 서비스 목표

## 핵심 목표

* 사용자가 특정 정보의 신뢰도를 빠르게 판단할 수 있도록 지원
* URL 기반의 간단한 검증 경험 제공
* AI 기반 분석 결과를 시각적으로 이해하기 쉽게 제공
* 가짜뉴스 판별 근거를 리포트 형태로 제공

---

# 3. 핵심 사용자 흐름

```text
메인 화면
→ URL 입력
→ 검증 요청
→ 분석 진행 화면
→ 검증 결과 화면
→ 상세 리포트 및 원문 뷰어 확인
```

---

# 4. 주요 화면 구성

# 4.1 메인 화면

## 목적

사용자가 검증할 URL을 입력하는 시작 화면입니다.

## UI 구성

```text
[서비스 로고]

“검증하고 싶은 뉴스·게시글 URL을 입력하세요.”

[ URL 입력창 ]

[ 검증하기 버튼 ]
```

## 주요 기능

| 기능     | 설명           |
| ------ | ------------ |
| URL 입력 | 사용자가 링크 입력   |
| URL 검증 | URL 형식 검사    |
| 분석 요청  | 검증 API 호출    |
| 예시 안내  | 지원 가능한 링크 안내 |

## 특징

* ChatGPT 스타일 중앙 입력 UI 사용 가능
* 최대한 단순하고 직관적인 구조 유지

---

# 4.2 분석 진행 화면

## 목적

사용자에게 현재 AI 분석이 진행 중임을 시각적으로 전달합니다.

## UI 예시

```text
입력한 URL을 분석 중입니다.

1. 본문 수집 중
2. 출처 확인 중
3. AI 분석 중
4. 리포트 생성 중
```

## 주요 기능

| 기능       | 설명          |
| -------- | ----------- |
| 로딩 애니메이션 | 분석 진행 표시    |
| 단계 표시    | 현재 분석 단계 출력 |
| 상태 메시지   | 사용자 대기 유도   |

## 비고

프로토타입 단계에서는 복잡한 비동기 큐 시스템 대신 단순 요청 처리 기반으로 구현 가능합니다.

---

# 4.3 검증 결과 화면

## 목적

AI 분석 결과를 사용자에게 직관적으로 제공하는 화면입니다.

## UI 구성

```text
[검증 결과]

신뢰도 점수: 72점 / 100점
판정 결과: 주의 필요

[요약 리포트]
일부 주장에 대한 근거가 부족하며,
출처 검증이 필요합니다.

[세부 분석 결과]
- 출처 신뢰도
- 주장 일관성
- 선동 표현 분석
- 이미지 조작 가능성
- 외부 근거 확인

[원문 뷰어]
사용자가 입력한 실제 본문 표시
```

---

# 5. 결과 표현 체계

# 5.1 100점 기반 신뢰도 점수

|  점수 구간 | 결과 표현       | 설명                    |
| -----: | ----------- | --------------------- |
| 80~100 | 신뢰 가능       | 주요 주장과 출처가 비교적 안정적    |
|  60~79 | 주의 필요       | 일부 근거 부족 또는 과장 가능성 존재 |
|  40~59 | 의심 필요       | 신뢰하기 어려운 요소 존재        |
|   0~39 | 가짜뉴스 가능성 높음 | 허위 가능성이 높음            |

---

# 5.2 세부 분석 항목

| 항목      | 설명                |
| ------- | ----------------- |
| 출처 신뢰도  | 언론사·게시 위치·작성자 신뢰성 |
| 주장 분석   | 핵심 주장 추출 및 논리 검토  |
| 근거 분석   | 본문 내 근거·출처 존재 여부  |
| 표현 분석   | 과장·선동·감정 유도 표현 여부 |
| 멀티모달 분석 | 이미지·썸네일 조작 가능성    |
| 종합 판단   | 전체 분석 결과 기반 최종 판정 |

---

# 6. 기술 스택

# 6.1 백엔드

| 항목     | 기술         |
| ------ | ---------- |
| 프레임워크  | FastAPI    |
| ORM    | SQLAlchemy |
| 데이터베이스 | SQLite     |
| 서버     | Uvicorn    |
| 템플릿 엔진 | Jinja2     |

## 설계 원칙

* FastAPI 기반 모놀리식 구조 사용
* 단순성과 빠른 프로토타입 구현 우선
* 내부 기능은 모듈화하여 병합 충돌 최소화
* AI 분석 기능은 별도 인터페이스로 분리

---

# 6.2 프론트엔드

| 항목    | 기술              |
| ----- | --------------- |
| 마크업   | HTML            |
| 스타일   | CSS             |
| 동적 처리 | JavaScript      |
| 렌더링   | Jinja2 Template |

## 비고

프로토타입 목적상 React·Vue 등의 SPA 구조는 필수가 아닙니다.

---

# 7. 시스템 아키텍처

# 7.1 전체 구조

```text
사용자
 ↓
FastAPI 웹 앱
 ↓
URL 수집 모듈
 ↓
AI Agent 연동 모듈
 ↓
점수 계산 모듈
 ↓
리포트 생성 모듈
 ↓
결과 화면 + 원문 뷰어
```

---

# 7.2 설계 방향

## 모놀리식 구조 채택

* 초기 개발 속도를 위해 단일 FastAPI 프로젝트로 구성
* 단, 기능별 모듈을 명확히 분리하여 유지보수성과 병합 편의성을 확보

## AI 분석 기능 분리

AI Agent 또는 Multi-modal LLM 연동은 별도 모듈로 분리합니다.

이유:

* AI 담당 인원이 별도로 존재할 수 있음
* Python 외 Java, JavaScript 기반 서버와도 연동 가능해야 함
* 이후 MSA 구조로 분리 가능하도록 고려 필요

---

# 8. 디렉터리 구조

```text
app/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routers/
│   ├── page.py
│   └── analysis.py
├── services/
│   ├── crawler_service.py
│   ├── analysis_service.py
│   ├── scoring_service.py
│   └── report_service.py
├── agents/
│   ├── base.py
│   ├── local_agent.py
│   └── external_agent_client.py
├── analyzers/
│   ├── base.py
│   ├── source_analyzer.py
│   ├── claim_analyzer.py
│   ├── expression_analyzer.py
│   └── multimodal_analyzer.py
├── templates/
│   ├── index.html
│   ├── loading.html
│   └── result.html
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── main.js
```

---

# 9. 주요 모듈 역할

# 9.1 URL 수집 모듈

```text
crawler_service.py
```

## 역할

* URL 접근
* 제목·본문·이미지 추출
* 메타데이터 수집
* 수집 실패 처리

---

# 9.2 AI 분석 모듈

```text
analysis_service.py
```

## 역할

* 수집 데이터 분석 요청
* 각 분석기 결과 통합
* 최종 분석 데이터 반환

---

# 9.3 AI Agent 연동 모듈

```text
agents/
```

## 역할

* Multi-modal LLM 호출
* 외부 AI 서버 연동
* 분석 요청/응답 처리

## 지원 구조

| 방식                 | 설명              |
| ------------------ | --------------- |
| Local Agent        | Python 내부 함수 기반 |
| External Agent API | 외부 HTTP API 호출  |
| Mock Agent         | 발표용 임시 결과 반환    |

---

# 9.4 점수 산정 모듈

```text
scoring_service.py
```

## 역할

* 분석 결과 기반 점수 계산
* 항목별 가중치 적용
* 최종 신뢰도 산출

## 예시 구조

```python
SCORING_RULES = {
    "source_reliability": {
        "weight": 25,
        "label": "출처 신뢰도",
    },
    "claim_consistency": {
        "weight": 25,
        "label": "주장 일관성",
    },
    "evidence_quality": {
        "weight": 20,
        "label": "근거 품질",
    },
    "expression_risk": {
        "weight": 15,
        "label": "선동 표현 위험도",
    },
    "multimodal_risk": {
        "weight": 15,
        "label": "멀티모달 조작 가능성",
    },
}
```

---

# 9.5 리포트 생성 모듈

```text
report_service.py
```

## 역할

* 분석 결과를 사용자 친화적 문장으로 변환
* 최종 요약 리포트 생성
* 화면 출력용 데이터 생성

---

# 10. AI Agent 인터페이스 규격

# 10.1 요청 예시

```json
{
  "url": "https://example.com/news/123",
  "title": "기사 제목",
  "content": "수집된 본문",
  "images": [
    "https://example.com/image.jpg"
  ]
}
```

---

# 10.2 응답 예시

```json
{
  "source_reliability": {
    "score": 80,
    "summary": "출처가 비교적 명확합니다."
  },
  "claim_consistency": {
    "score": 65,
    "summary": "일부 주장 근거가 부족합니다."
  },
  "evidence_quality": {
    "score": 60,
    "summary": "외부 검증 근거가 제한적입니다."
  },
  "expression_risk": {
    "score": 70,
    "summary": "자극적인 표현이 일부 포함되어 있습니다."
  },
  "multimodal_risk": {
    "score": 75,
    "summary": "이미지 조작 가능성은 낮습니다."
  }
}
```

---

# 11. 데이터베이스 설계

# 11.1 AnalysisResult

| 컬럼           | 타입       | 설명         |
| ------------ | -------- | ---------- |
| id           | Integer  | 기본 키       |
| url          | String   | 입력 URL     |
| title        | String   | 콘텐츠 제목     |
| content      | Text     | 수집 본문      |
| score        | Integer  | 최종 점수      |
| result_label | String   | 최종 판정      |
| report_json  | Text     | 분석 결과 JSON |
| created_at   | DateTime | 생성 시각      |

---

# 12. API 명세

# 12.1 메인 화면

```http
GET /
```

## 설명

URL 입력 화면 반환

---

# 12.2 URL 분석 요청

```http
POST /analysis
```

## 요청 예시

```json
{
  "url": "https://example.com/news/123"
}
```

## 처리 흐름

```text
URL 검증
→ 본문 수집
→ AI 분석 요청
→ 점수 계산
→ 리포트 생성
→ 결과 저장
→ 결과 페이지 반환
```

---

# 12.3 결과 조회

```http
GET /analysis/{analysis_id}
```

## 설명

저장된 분석 결과 조회

---

# 13. 분석 기준 확장 구조

분석 항목은 독립 클래스로 관리합니다.

```python
class BaseAnalyzer:
    name: str

    def analyze(self, content: dict) -> dict:
        raise NotImplementedError
```

예시:

```python
class SourceAnalyzer(BaseAnalyzer):
    name = "source_reliability"

    def analyze(self, content: dict) -> dict:
        return {
            "score": 80,
            "summary": "출처가 비교적 명확합니다.",
            "risk": "low",
        }
```

---

# 14. 프로토타입 구현 범위

# 포함 기능

| 기능          | 포함 여부 |
| ----------- | ----- |
| URL 입력 UI   | 포함    |
| URL 분석 요청   | 포함    |
| 본문 수집       | 포함    |
| AI 분석       | 포함    |
| 100점 신뢰도 표시 | 포함    |
| 리포트 출력      | 포함    |
| 원문 뷰어       | 포함    |
| 결과 저장       | 포함    |

---

# 제외 기능

| 기능         | 제외 사유       |
| ---------- | ----------- |
| 로그인        | 핵심 기능과 무관   |
| 회원가입       | 불필요         |
| 관리자 페이지    | 프로토타입 범위 초과 |
| 결제 기능      | 불필요         |
| 복잡한 비동기 처리 | 개발 난이도 증가   |
| OCR 직접 구현  | 범위 초과       |

---

# 15. 핵심 설계 원칙

1. 검증 기능 중심 서비스 구성
2. FastAPI 기반 단순 구조 유지
3. 내부 기능 모듈화
4. AI Agent 연동부 독립화
5. 언어 독립적 연동 가능 구조 확보
6. 점수 기준 및 가중치 수정 가능 구조 채택
7. 이후 MSA 전환 가능성 고려

---

# 16. 최종 서비스 정의

> 본 서비스는 사용자가 입력한 뉴스·SNS·게시글 URL의 본문과 첨부 정보를 AI 기반으로 분석하여, 가짜뉴스 가능성을 100점 신뢰도와 상세 리포트 형태로 제공하는 FastAPI 기반 웹 검증 플랫폼입니다.
