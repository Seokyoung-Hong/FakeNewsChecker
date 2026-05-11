import httpx

from app.config import HIVE_API_KEY

HIVE_API_URL = "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"


def _to_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _class_probability(cls: object) -> float | None:
    if not isinstance(cls, dict):
        return None

    # Standard response style (v3 docs): {"class": "ai_generated", "score": 0.12}
    if cls.get("class") and "score" in cls:
        return _to_number(cls.get("score"))

    # Legacy / uncertain style observed in prior code paths.
    fallback = _to_number(cls.get("value"))
    if fallback is not None:
        return fallback

    # Some payloads express classes as a map, e.g. {"ai_generated": 0.12}
    for key, value in cls.items():
        if key in {"class", "score", "value", "meta", "time"}:
            continue
        if isinstance(value, (int, float, str)):
            return _to_number(value)
    return None


def _extract_output_items(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []

    outputs: list[object] = []

    output_field = payload.get("output")
    if output_field is not None:
        outputs.append(output_field)

    status = payload.get("status")
    if isinstance(status, dict):
        if status.get("output") is not None:
            outputs.append(status.get("output"))
        response = status.get("response")
        if isinstance(response, dict) and response.get("output") is not None:
            outputs.append(response.get("output"))

    flattened: list[dict[str, object]] = []
    for output in outputs:
        if isinstance(output, dict):
            classes = output.get("classes")
            if isinstance(classes, list):
                flattened.extend([item for item in classes if isinstance(item, dict)])
            continue

        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict):
                    classes = item.get("classes")
                    if isinstance(classes, list):
                        flattened.extend([item for item in classes if isinstance(item, dict)])
    return flattened


def _class_name(cls: dict[str, object]) -> str | None:
    explicit = cls.get("class")
    if isinstance(explicit, str):
        return explicit

    for key in ("ai_generated", "deepfake"):
        if key in cls:
            return key

    return None


def analyze_images(image_urls: list[str]) -> dict[str, object]:
    if not image_urls:
        return {"score": 100, "summary": "분석할 이미지가 없습니다.", "risk": "low"}

    if not HIVE_API_KEY:
        return {"score": 50, "summary": "Hive API 키가 없어 이미지 분석을 건너뜁니다.", "risk": "unknown"}

    headers = {
        "Authorization": f"Bearer {HIVE_API_KEY}",
        "Content-Type": "application/json",
    }

    ai_scores = []
    deepfake_scores = []
    last_error: str | None = None

    for img_url in image_urls[:3]:
        try:
            resp = httpx.post(
                HIVE_API_URL,
                headers=headers,
                json={"input": [{"media_url": img_url}]},
                timeout=15,
            )
            if resp.status_code != 200:
                body = resp.text[:200]
                try:
                    body_json = resp.json()
                    message = body_json.get("message") if isinstance(body_json, dict) else None
                    if isinstance(message, str) and message:
                        body = message
                except Exception:
                    pass
                last_error = f"{resp.status_code}: {body}"
                continue

            data = resp.json()
            classes = _extract_output_items(data)

            for cls in classes:
                if not isinstance(cls, dict):
                    continue

                cls_name = _class_name(cls)
                probability = _class_probability(cls)

                if not isinstance(probability, (int, float)):
                    continue

                if cls_name == "ai_generated":
                    ai_scores.append(float(probability))
                elif cls_name == "deepfake":
                    deepfake_scores.append(float(probability))
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    if not ai_scores and not deepfake_scores:
        if last_error:
            return {
                "score": 50,
                "summary": f"이미지 분석에 실패했습니다. ({last_error})",
                "risk": "unknown",
            }
        return {"score": 50, "summary": "이미지 분석에 실패했습니다.", "risk": "unknown"}

    avg_ai = sum(ai_scores) / len(ai_scores) if ai_scores else 0.0
    avg_deepfake = sum(deepfake_scores) / len(deepfake_scores) if deepfake_scores else 0.0
    risk_score = max(avg_ai, avg_deepfake)

    if avg_ai >= 0.9:
        summary = f"AI 생성 이미지로 강하게 의심됩니다. (확률 {avg_ai:.0%})"
        risk = "high"
    elif avg_deepfake >= 0.9:
        summary = f"딥페이크 가능성이 높습니다. (확률 {avg_deepfake:.0%})"
        risk = "high"
    elif risk_score >= 0.5:
        summary = f"이미지 조작 가능성이 일부 존재합니다. (확률 {risk_score:.0%})"
        risk = "medium"
    else:
        summary = "이미지 조작 가능성은 낮습니다."
        risk = "low"

    return {"score": round((1 - risk_score) * 100), "summary": summary, "risk": risk}
