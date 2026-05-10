import httpx
from app.config import HIVE_API_KEY

HIVE_API_URL = "https://api.thehive.ai/api/v3/hive/ai-generated-and-deepfake-content-detection"


def analyze_images(image_urls: list[str]) -> dict:
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

    for img_url in image_urls[:3]:
        try:
            resp = httpx.post(
                HIVE_API_URL,
                headers=headers,
                json={"input": [{"media_url": img_url}]},
                timeout=15,
            )
            data = resp.json()
            classes = data["output"][0]["classes"]

            for cls in classes:
                if cls["class"] == "ai_generated":
                    ai_scores.append(cls["value"])
                elif cls["class"] == "deepfake":
                    deepfake_scores.append(cls["value"])
        except Exception:
            pass

    if not ai_scores and not deepfake_scores:
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