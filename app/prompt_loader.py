from __future__ import annotations

import logging
import os
from pathlib import Path
from string import Template
from typing import Final


logger = logging.getLogger(__name__)

_PROMPT_DIR_ENV: Final = "PROMPT_DIR"
_PROMPT_DIR = "prompts"

_DEFAULT_PROMPTS: dict[str, str] = {
    "gemini_text": """너는 텍스트 기반 가짜뉴스 판별 도우미야. 아래 콘텐츠가 실제로 허위이거나, 과장되었거나, 오해를 유발할 가능성이 있는지 분석해줘.

제목: $title
URL: $url
기준일(분석 기준일): $analysis_date
본문:
$text

선행 멀티모달 분석 결과:
- risk: $multimodal_risk
- score: $multimodal_score
- summary: $multimodal_summary

중요 규칙:
- 학습 데이터에 없다는 이유만으로 허위라고 단정하지 마.
- 확인 가능한 근거 부족, 주장 모순, 맥락 왜곡, 과장·선동 표현은 강한 감점 요인이다.
- 판별 대상은 "기사/게시글의 가짜뉴스 가능성"이다.
- 판별은 출처 신뢰성, 주장 일관성, 근거의 질, 표현 위험을 중심으로 해라.
- 선행 멀티모달 결과가 있으면 기사와 이미지 맥락을 함께 반영해 multimodal_risk를 채워라.

각 항목 평가 기준:
- source_reliability: 출처와 작성 주체가 신뢰 가능한지, 기사 형식이 정상적인지
- claim_consistency: 제목, 본문, 핵심 주장 사이에 모순이나 맥락 왜곡이 없는지
- evidence_quality: 근거, 수치, 인용, 공식 출처, 교차 검증 가능성이 충분한지
- expression_risk: 선동/낚시성/공포 조장/단정적 표현이 많지 않은지 (적을수록 높은 점수)
- multimodal_risk: 이미지 내용, 이미지 속 텍스트, 기사 본문과 이미지 맥락 일치 여부, 조작 가능성 신호를 종합한 위험도

아래 JSON 형식으로만 응답해. 다른 말은 절대 하지 마:
{
  "overall_summary": {
    "verdict": "신뢰 가능 / 주의 필요 / 의심 필요 / 가짜뉴스 가능성 높음 중 하나",
    "reasons": ["핵심 근거 1", "핵심 근거 2", "핵심 근거 3"]
  },
  "source_reliability": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"},
  "claim_consistency": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"},
  "evidence_quality": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"},
  "expression_risk": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명"},
  "multimodal_risk": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}
}

점수 기준:
 - 100 = 가짜뉴스 가능성이 매우 낮음
 - 0 = 가짜뉴스 가능성이 매우 높음
""",

    "ollama_text": """너는 텍스트 기반 가짜뉴스 판별 도우미야. 아래 콘텐츠가 허위이거나, 과장되었거나, 오해를 유발할 가능성이 있는지 분석해줘.

제목: $title
URL: $url
기준일(분석 기준일): $analysis_date
본문:
$text

선행 멀티모달 분석 결과:
- risk: $multimodal_risk
- score: $multimodal_score
- summary: $multimodal_summary

중요 규칙:
- 학습 데이터에 없다는 이유만으로 허위라고 단정하지 마.
- 확인 가능한 근거 부족, 주장 모순, 맥락 왜곡, 과장·선동 표현은 강한 감점 요인이다.
- 판별 대상은 기사/게시글의 가짜뉴스 가능성이다.
- 본문에 없는 사람의 직함, 기관명, 사건 전개를 추정해서 보정하지 마.
- 원문에 없는 사실을 채워 넣지 말고, 불확실하면 불확실하다고 적어라.
- 일반적인 정치 기사나 속보 기사라는 이유만으로 과도하게 감점하지 마. 실제 본문에 드러난 근거와 표현만 기준으로 판단해라.
- 특정 주장에 대한 외부 검증이 본문에 부족하더라도, 곧바로 허위라고 단정하지 말고 "검증 근거 부족" 수준으로 표현해라.
- 선행 멀티모달 결과가 있으면 기사와 이미지 맥락을 함께 반영해 multimodal_risk를 채워라.
- 아래 JSON 형식으로만 응답해. 다른 말은 절대 하지 마.

응답 JSON 스키마:
{
  "overall_summary": {
    "verdict": "신뢰 가능 / 주의 필요 / 의심 필요 / 가짜뉴스 가능성 높음 중 하나",
    "reasons": ["핵심 근거 1", "핵심 근거 2", "핵심 근거 3"]
  },
  "source_reliability": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"},
  "claim_consistency": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"},
  "evidence_quality": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"},
  "expression_risk": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"},
  "multimodal_risk": {"score": 0에서 100 사이 정수, "summary": "한국어 2문장 설명", "risk": "low|medium|high"}
}

점수 기준:
- 100 = 가짜뉴스 가능성이 매우 낮음
- 0 = 가짜뉴스 가능성이 매우 높음""",
    "gemini_multimodal": """너는 이미지 기반 허위정보 판별 도우미야. 반드시 실제 이미지 내용과 기사 맥락을 함께 분석해라.

제목: $title
URL: $url
기준일(분석 기준일): $analysis_date
본문 요약:
$text

Hive 선행 분석 결과:
- score: $hive_score
- risk: $hive_risk
- summary: $hive_summary

중요 규칙:
- 이미지를 직접 보고 판단해라.
- Hive 결과는 참고 신호일 뿐이며 그대로 복사하거나 맹신하지 마라.
- 이미지 안의 텍스트, 장면, 편집 흔적, 합성 징후, 맥락 불일치를 중점 분석해라.
- 기사 맥락과 이미지 내용이 맞지 않으면 강한 감점 요인이다.
- JSON만 응답해라.

응답 JSON:
{
  "score": 0에서 100 사이 정수,
  "summary": "한국어 2문장 설명",
  "risk": "low|medium|high",
  "signals": ["핵심 시각 신호 1", "핵심 시각 신호 2"]
}
""",
    "ollama_multimodal": """너는 이미지 기반 허위정보 판별 도우미야. 반드시 실제 이미지 내용과 기사 맥락을 함께 분석해라.

제목: $title
URL: $url
기준일(분석 기준일): $analysis_date
본문 요약:
$text

Hive 선행 분석 결과:
- score: $hive_score
- risk: $hive_risk
- summary: $hive_summary

중요 규칙:
- 이미지를 직접 보고 판단해라.
- Hive 결과는 참고 신호일 뿐이며 그대로 복사하거나 맹신하지 마라.
- 이미지 안의 텍스트, 장면, 편집 흔적, 합성 징후, 맥락 불일치를 중점 분석해라.
- 기사 맥락과 이미지 내용이 맞지 않으면 강한 감점 요인이다.
- JSON만 응답해라.

응답 JSON:
{
  "score": 0에서 100 사이 정수,
  "summary": "한국어 2문장 설명",
  "risk": "low|medium|high",
  "signals": ["핵심 시각 신호 1", "핵심 시각 신호 2"]
}
""",
    "structured_json_system": "Return only valid JSON matching the provided schema.",
    "local_browser_navigation": """You are selecting the next navigation action to reach a news article body.
Return only valid JSON matching the schema.

Current URL: $current_url
Current title: $current_title
Current visible text excerpt:
$excerpt

Candidate targets:
$candidate_lines

Rules:
- Prefer opening a candidate that looks like a specific article headline.
- Avoid generic navigation, live blogs, category pages, sign-in, video, audio, and newsletters when possible.
- If no candidate appears promising, choose finish.
- action must be one of open_target, scroll, finish.
""",
    "hyperbrowser_fetch_article": "Extract the page title, the main article or post text, and every meaningful image URL that belongs to the article body, post body, or card-news/carousel slides. For Instagram or similar SNS posts, include every actual post/carousel image in order. Exclude profile pictures, author avatars, commenter avatars, icons, logos, navigation images, and ad images.",
}


def _get_prompt_root() -> Path:
    """Return the prompt root directory from env var or package fallback."""

    configured_dir = os.getenv(_PROMPT_DIR_ENV, "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser()
    return Path(__file__).resolve().parent / _PROMPT_DIR


def _normalize_prompt_name(name: str) -> str:
    if name.endswith(".txt"):
        return name
    return f"{name}.txt"


def _read_prompt_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _load_prompt_text(name: str) -> str:
    prompt_dir = _get_prompt_root()
    file_path = prompt_dir / _normalize_prompt_name(name)
    if not file_path.is_file():
        default = _DEFAULT_PROMPTS.get(name)
        if default is not None:
            logger.warning(
                "Prompt file missing; using built-in fallback prompt",
                extra={"event": "prompt_file_missing", "prompt_path": str(file_path), "prompt_name": name},
            )
            return default
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    return _read_prompt_file(str(file_path))


def load_prompt(name: str, **params: object) -> str:
    """Load a prompt template and render variables via safe substitution."""

    template = _load_prompt_text(name)
    try:
        return Template(template).substitute(**params)
    except KeyError as exc:
        missing_key = exc.args[0] if exc.args else "unknown"
        raise ValueError(
            f"Prompt '{name}' is missing template variable '{missing_key}'."
        ) from exc


__all__ = ["load_prompt"]
