# Python 뉴스 분석 구현 가이드

이 문서는 **아주 단순하게** 설명합니다.

복잡한 프로젝트 구조는 신경 쓰지 않아도 됩니다.

핵심은 이것입니다.

> **`downloaded_news` 폴더 안의 세부 폴더 하나만 읽어서 분석 코드를 만들면 됩니다.**

예를 들면 이런 식입니다.

```text
downloaded_news/
└── 5c40cadb-1bbc-5e30-a62d-93a52a811ad5/
    ├── article.txt
    ├── metadata.json
    ├── structured_data.json
    ├── image_urls.json
    └── images/
```

여기서 중요한 것은 **세부 폴더 이름**입니다.

이 이름만 알면 됩니다.

- CLI에서 받을 수도 있고
- 함수 인자로 받을 수도 있고
- 다른 코드에서 문자열로 넘겨줄 수도 있습니다

즉, 아래 둘 다 괜찮습니다.

```bash
python analyze_news.py 5c40cadb-1bbc-5e30-a62d-93a52a811ad5
```

또는

```python
analyze_news("5c40cadb-1bbc-5e30-a62d-93a52a811ad5")
```

---

## 1. 무엇을 읽으면 되나요?

분석 코드는 우선 아래 파일만 보면 됩니다.

### 1) `article.txt`
- 가장 중요한 파일입니다.
- 뉴스 본문 텍스트가 들어 있습니다.
- 보통 이 파일을 중심으로 분석합니다.

### 2) `structured_data.json`
- 구조화된 제목, 본문, 이미지 정보가 들어 있습니다.
- 이미지 관련 정보는 이 파일을 기준으로 보면 됩니다.

### 3) `metadata.json`
- 수집 시각, 원본 URL, 기타 메타데이터가 들어 있습니다.
- 꼭 처음부터 쓰지 않아도 됩니다.

### 4) `image_urls.json`
- 이미지 URL 목록입니다.
- 필요하면 참고하면 됩니다.

### 5) `images/`
- 실제로 저장된 이미지 파일 폴더입니다.
- 이미지 분석이 필요할 때만 보면 됩니다.

---

## 2. 가장 쉬운 분석 방식

처음에는 이렇게 생각하면 됩니다.

1. 폴더 이름 하나를 받는다.
2. `downloaded_news/<폴더이름>` 경로를 만든다.
3. `article.txt`를 읽는다.
4. 필요하면 `structured_data.json`도 읽는다.
5. 그 내용을 바탕으로 분석 결과를 만든다.

이것만 해도 충분합니다.

---

## 3. 아주 단순한 예시 코드

아래 예시는 **폴더 이름 하나만 받아서** 본문과 구조화 데이터를 읽는 가장 쉬운 형태입니다.

```python
from pathlib import Path
import json
import sys


def analyze_news(folder_name: str) -> dict:
    base_dir = Path("downloaded_news") / folder_name

    article_text = (base_dir / "article.txt").read_text(encoding="utf-8")
    structured_data = json.loads(
        (base_dir / "structured_data.json").read_text(encoding="utf-8")
    )

    title = structured_data.get("title", "")
    image_urls = structured_data.get("image_urls", [])

    result = {
        "folder_name": folder_name,
        "title": title,
        "text_length": len(article_text),
        "image_count": len(image_urls),
        "summary": article_text[:200],
    }

    return result


if __name__ == "__main__":
    folder_name = sys.argv[1]
    result = analyze_news(folder_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

이 코드는 아주 단순합니다.

- `downloaded_news/<폴더이름>`으로 들어가고
- `article.txt`를 읽고
- `structured_data.json`을 읽고
- 간단한 결과를 출력합니다

---

## 4. 함수로만 써도 됩니다

CLI가 싫으면 함수만 써도 됩니다.

```python
from pathlib import Path
import json


def analyze_news(folder_name: str) -> dict:
    base_dir = Path("downloaded_news") / folder_name

    article_text = (base_dir / "article.txt").read_text(encoding="utf-8")
    structured_data = json.loads(
        (base_dir / "structured_data.json").read_text(encoding="utf-8")
    )

    return {
        "title": structured_data.get("title", ""),
        "content": article_text,
        "images": structured_data.get("image_urls", []),
    }


result = analyze_news("5c40cadb-1bbc-5e30-a62d-93a52a811ad5")
print(result["title"])
```

---

## 5. 처음에는 무엇을 분석하면 되나요?

처음부터 어렵게 하지 말고 아래 정도만 해 보세요.

### 가장 쉬운 버전
- 제목 출력하기
- 본문 길이 세기
- 이미지 개수 세기

### 그 다음 버전
- 본문 앞 3문장만 요약하기
- 특정 키워드가 있는지 찾기
- 감정적인 표현이 많은지 보기

### 이미지까지 보고 싶다면
- `structured_data.json`의 `image_urls` 보기
- `images/` 폴더 안 실제 파일 개수 보기

---

## 6. 실제로는 어떤 파일이 제일 중요하나요?

처음에는 아래 우선순위로 보면 됩니다.

1. `article.txt`
2. `structured_data.json`
3. `images/`
4. `metadata.json`
5. `image_urls.json`

즉, **본문 + 구조화 데이터**만 읽어도 대부분의 시작은 충분합니다.

---

## 7. 실수하지 말아야 할 점

### 1) 루트 폴더 전체를 분석하지 마세요
`downloaded_news` 전체를 한 번에 읽으려 하지 말고,
**그 안의 세부 폴더 하나만** 분석하세요.

### 2) 폴더 이름을 직접 넘겨받으세요
하드코딩만 하지 말고 아래 둘 중 하나로 받는 것이 좋습니다.

- CLI 인자
- 함수 인자

### 3) 이미지 정보는 `structured_data.json` 기준으로 보세요
이미지 관련 판단은 `structured_data.json` 안의 값을 먼저 보면 됩니다.

---

## 8. 한 문장으로 끝내면

> **분석 코드는 `downloaded_news/<폴더이름>` 하나를 입력받고, 그 안의 `article.txt`와 `structured_data.json`을 읽으면 됩니다.**

이렇게만 이해하면 충분합니다.
