# 프로젝트 지식 베이스

**생성일:** 2026-05-09  
**커밋 상태:** uncommitted  
**브랜치:** main

## 개요

이 저장소는 뉴스 기사·SNS 게시글·블로그 URL을 입력받아 신뢰도 스타일의 결과 페이지를 보여주는 FastAPI 프로토타입입니다. 현재 구현은 이미 실행 가능한 Docker Compose 런타임과 `app/` 패키지를 포함하고 있으며, 분석 로직은 외부 네트워크 없이 동작하는 결정론적 오프라인 스텁입니다.

## 프로젝트 정의

- 제품 목표: URL 기반 검증 경험과 100점 기준 신뢰도 리포트 제공
- 현재 구현 범위: 홈 화면, URL 제출, 결정론적 분석 실행, 결과 페이지 렌더링, 오류 화면 렌더링
- 제외 범위: 로그인, 회원가입, 관리자 기능, 결제, 복잡한 비동기 큐, 실제 OCR/멀티모달 판별, 실서비스 수준의 외부 AI 연동
- 주 실행 계약: Docker Compose로 웹 앱 실행

## 현재 상태

- `app/` 패키지가 존재하며 FastAPI 앱이 구현되어 있습니다.
- 현재 웹 엔트리포인트는 `app.main:app`입니다.
- `docker-compose.yml`과 `Dockerfile`이 존재하며 실제로 Docker 런타임이 구성되어 있습니다.
- 루트 `README.md`는 비어 있지 않으며 현재 프로토타입 설명 문서입니다.
- 루트 `main.py`는 단순 플레이스홀더 출력용 파일입니다.
- 결과 저장소는 `InMemoryAnalysisResultRepository`이며 영속 저장이 아닙니다.
- `app/database.py`, `app/models.py`, `app/agents/external_agent_client.py`는 미래 구현을 위한 플레이스홀더/시드 단계입니다.

## 현재 동작하는 요청 흐름

```text
GET /
→ POST /analysis
→ DeterministicAnalysisService.run()
→ DeterministicCrawlerService.collect()
→ Analyzer + LocalAgent 기준별 분석
→ DeterministicScoringService.score()
→ DeterministicReportService.build_report()
→ InMemoryAnalysisResultRepository.create()
→ 303 redirect to GET /analysis/{analysis_id}
```

## 현재 루트 구조

```text
./
├── app/
│   ├── agents/
│   ├── analyzers/
│   ├── routers/
│   ├── services/
│   ├── static/
│   ├── templates/
│   ├── database.py
│   ├── dependencies.py
│   ├── main.py
│   ├── models.py
│   ├── repositories.py
│   └── schemas.py
├── docs/
│   └── IMPLEMENTATION_GUIDE_ANALYSIS_PYTHON.md
├── CONTRIBUTING.md
├── FunctionalSpec.md
├── README.md
├── docker-compose.yml
├── Dockerfile
├── main.py
├── pyproject.toml
└── uv.lock
```

## 어디를 봐야 하는가

| 작업 목적 | 위치 | 비고 |
|---|---|---|
| 현재 실행 방식 이해 | `docker-compose.yml`, `Dockerfile`, `app/main.py` | 실제 런타임 기준 |
| 홈/결과 화면 흐름 확인 | `app/routers/page.py`, `app/routers/analysis.py`, `app/templates/` | 서버 렌더링 기반 |
| 현재 분석 파이프라인 확인 | `app/services/`, `app/analyzers/`, `app/agents/local_agent.py` | 전부 오프라인 결정론적 스텁 |
| 데이터 계약 확인 | `app/schemas.py` | 현재 파이프라인의 핵심 DTO |
| 저장 방식 확인 | `app/repositories.py` | 메모리 저장소 |
| 장기 제품 목표 확인 | `FunctionalSpec.md` | 현재 구현보다 넓은 목표 문서 |
| 기여 절차 확인 | `CONTRIBUTING.md` | 온보딩/검증 기준 |
| 실제 기능 확장 지침 확인 | `docs/IMPLEMENTATION_GUIDE_ANALYSIS_PYTHON.md` | 구현 대상별 상세 가이드 |

## 코드 맵

| 심볼/구성 | 종류 | 위치 | 역할 |
|---|---|---|---|
| `app` | FastAPI 인스턴스 | `app/main.py` | 정적 파일 마운트 및 라우터 등록 |
| `create_analysis` | 라우트 핸들러 | `app/routers/analysis.py` | URL 제출 처리, 분석 실행, 리다이렉트 |
| `analysis_result_page` | 라우트 핸들러 | `app/routers/analysis.py` | 저장된 결과 조회 및 렌더링 |
| `DeterministicAnalysisService` | 서비스 | `app/services/analysis_service.py` | 전체 파이프라인 오케스트레이션 |
| `DeterministicCrawlerService` | 서비스 | `app/services/crawler_service.py` | URL 기반 스텁 수집 결과 생성 |
| `LocalAgent` | 에이전트 | `app/agents/local_agent.py` | 기준별 정적 점수 계산 |
| `DeterministicScoringService` | 서비스 | `app/services/scoring_service.py` | 가중 평균 총점 계산 |
| `DeterministicReportService` | 서비스 | `app/services/report_service.py` | 결과 페이지용 리포트 조립 |
| `InMemoryAnalysisResultRepository` | 저장소 | `app/repositories.py` | 메모리 저장/조회 |

## 규칙과 관례

- Python 전용 저장소입니다.
- 현재 의존성은 `fastapi`, `jinja2`, `python-multipart`, `uvicorn`이 선언되어 있습니다.
- 로컬 Python 지원 범위는 `>=3.11,<3.13`입니다.
- 현재 UI는 Jinja2 서버 렌더링 기반이며 SPA 전환은 전제되어 있지 않습니다.
- 실제 기능이 추가되더라도 라우터는 얇게 유지하고 서비스/에이전트/분석기 계층에 책임을 배치하는 방향이 현재 구조와 맞습니다.
- 현재 프로토타입의 중요한 특성은 **오프라인**, **결정론적**, **동기식**, **메모리 저장**입니다.

## 주의할 안티패턴

- 현재 구현이 없는 외부 AI 호출을 이미 존재하는 것처럼 문서화하거나 가정하지 말 것
- `root main.py`를 실제 웹 서버 엔트리포인트로 취급하지 말 것
- 메모리 저장소를 영속 저장처럼 다루지 말 것
- 비동기 큐나 백그라운드 워커를 현재 구현으로 오해하지 말 것
- `FunctionalSpec.md`의 장기 목표를 곧바로 현재 상태로 서술하지 말 것
- 라우터에 분석 로직을 직접 넣어 계층 분리를 무너뜨리지 말 것

## 현재 실행 명령

```bash
docker compose up --build
```

## 참고 메모

- `GET /analysis/{analysis_id}`는 저장소가 초기화되었거나 ID가 없으면 404 오류 화면을 렌더링합니다.
- 홈 화면의 로딩 오버레이는 `app/static/js/main.js`에서 제어하는 브라우저 측 연출이며, 서버의 별도 진행 상태 추적은 없습니다.
- 실제 데이터베이스 도입과 외부 분석기 연동은 아직 구현되지 않았고, 관련 자리만 준비되어 있습니다.
