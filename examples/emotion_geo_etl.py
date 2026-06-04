"""Example: convert an emotion prediction into map-friendly fields.

This file is only an integration example. The active worker path lives in
`ai/infra/mq_emotion.py`.
"""

from ai.emotion_policy import stage1_of


PALETTE = {
    ("긍정", "강"): "#1565C0",
    ("긍정", "보통"): "#42A5F5",
    ("긍정", "약"): "#90CAF9",
    ("부정", "강"): "#B71C1C",
    ("부정", "보통"): "#E53935",
    ("부정", "약"): "#FFCDD2",
}


def enrich_record(record: dict, prediction: dict) -> dict:
    label = prediction["label"]
    probability = float(prediction["prob"])
    strength = prediction.get("strength", "보통")

    stage1 = stage1_of(label)
    sign = 1 if stage1 == "긍정" else -1

    return {
        **record,
        "emotion_label": label,
        "emotion_score": probability,
        "emotion_stage1": stage1,
        "valence": round(sign * probability, 4),
        "color_hex": PALETTE.get((stage1, strength), "#BDBDBD"),
    }
