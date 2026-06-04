import json
import unittest
from pathlib import Path

from ai.emotion_policy import LABELS, stage1_of, valence_of
from ai.infra.emotion_message import (
    UNKNOWN_LABEL,
    build_emotion_result,
    inspect_model_dir,
    is_reliable_prediction,
    parse_emotion_request,
)
from ai.infra.insight_message import parse_insight_request
from ai.infra.insight_policy import assess_evidence, build_light_advice, place_valences
from ai.recommender.request_parser import parse_request
from ai.recommender.recommender import _emo_component, _social_score, recommend_top_n
from ai.recommender.schema import Place, to_label_idx
from scripts.analyze_emotion_errors import summarize_errors
from scripts.audit_emotion_data import analyze_rows
from scripts.build_emotion_boundary_cases import build_boundary_cases
from scripts.build_emotion_error_template import build_error_template, read_domain_eval
from scripts.build_recommender_eval_cases import build_cases, load_logs
from scripts.evaluate_emotion_domain_model import metrics_for, threshold_report
from scripts.evaluate_boundary_review import evaluate_review
from scripts.evaluate_recommender import evaluate_cases, load_cases
from scripts.prepare_emotion_dataset import clean_rows, stratified_split

ROOT = Path(__file__).resolve().parents[1]


def place(place_id: int, name: str, category: str) -> Place:
    return Place(
        placeId=place_id,
        name=name,
        category=category,
        latitude=37.5,
        longitude=127.0,
    )


def recommend_from_payload(payload: dict):
    parsed = parse_request(payload)
    return recommend_top_n(
        user_id=parsed["user_id"],
        candidate_places=parsed["candidates"],
        recent_emotion_idx=parsed["recent_idx"],
        recent_emotion_score=parsed["recent_score"],
        fav_categories=parsed["fav_categories"],
        scrap_place_ids=parsed["scrap_place_ids"],
        place_positive_ratio=parsed["pos_ratio"],
        followed_positive_count=parsed["followed_pos_count"],
        top_n=parsed["top"],
        debug=parsed["debug"],
        recent_emotion_reliable=parsed["recent_reliable"],
    )


class RecommenderTests(unittest.TestCase):
    def test_emotion_policy_labels_match_model_order(self):
        self.assertEqual(LABELS, ["기쁨", "놀람", "분노", "불안", "상처", "슬픔"])

    def test_negative_emotion_prioritizes_positive_places(self):
        candidates = [
            place(1, "busy cafe", "카페"),
            place(2, "quiet park", "공원"),
        ]

        result = recommend_top_n(
            user_id=7,
            candidate_places=candidates,
            recent_emotion_idx=to_label_idx("불안"),
            recent_emotion_score=0.9,
            fav_categories={"카페": 10},
            scrap_place_ids=set(),
            place_positive_ratio={1: 0.2, 2: 0.95},
            followed_positive_count={},
            top_n=2,
            debug=True,
        )

        self.assertEqual(result[0]["placeId"], 2)
        self.assertGreater(result[0]["reason"]["pos_ratio"], result[1]["reason"]["pos_ratio"])

    def test_positive_emotion_uses_category_and_scrap_signals(self):
        candidates = [
            place(1, "museum", "미술관"),
            place(2, "favorite cafe", "카페"),
        ]

        result = recommend_top_n(
            user_id=7,
            candidate_places=candidates,
            recent_emotion_idx=to_label_idx("기쁨"),
            recent_emotion_score=0.8,
            fav_categories={"카페": 8, "미술관": 1},
            scrap_place_ids={2},
            place_positive_ratio={1: 0.8, 2: 0.75},
            followed_positive_count={1: 1, 2: 1},
            top_n=2,
            debug=True,
        )

        self.assertEqual(result[0]["placeId"], 2)
        self.assertEqual(result[0]["reason"]["scrap"], 1.0)
        self.assertGreater(result[0]["reason"]["cat_pref"], result[1]["reason"]["cat_pref"])

    def test_surprise_is_weak_positive_policy(self):
        self.assertEqual(stage1_of("놀람"), "긍정")
        self.assertEqual(valence_of("놀람"), 0.2)

        joy_score = _emo_component(to_label_idx("기쁨"), 0.9, pos_ratio=0.5, cat_pref=1.0)
        surprise_score = _emo_component(to_label_idx("놀람"), 0.9, pos_ratio=0.5, cat_pref=1.0)

        self.assertGreater(joy_score, 0.5)
        self.assertGreater(surprise_score, 0.5)
        self.assertLess(surprise_score, joy_score)

    def test_social_score_is_capped(self):
        self.assertEqual(_social_score(1, {1: 0}), 0.0)
        self.assertAlmostEqual(_social_score(1, {1: 2}), 2 / 3)
        self.assertEqual(_social_score(1, {1: 5}), 1.0)

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(ValueError):
            to_label_idx("알수없음")

    def test_emotion_request_aliases_are_parsed_without_model(self):
        req = parse_emotion_request({"memoId": "17", "text": "오늘 공원 산책이 좋았어"})

        self.assertEqual(req.memo_id, 17)
        self.assertEqual(req.content, "오늘 공원 산책이 좋았어")

    def test_emotion_result_includes_policy_fields(self):
        result = build_emotion_result(17, "놀람", 0.87654321)

        self.assertEqual(result["memoId"], 17)
        self.assertEqual(result["emotionLabel"], "놀람")
        self.assertEqual(result["emotionScore"], 0.876543)
        self.assertEqual(result["stage1"], "긍정")
        self.assertEqual(result["valence"], 0.2)
        self.assertEqual(result["safeLabel"], result["emotionLabel"])
        self.assertTrue(result["isReliable"])
        self.assertEqual(result["confidenceThreshold"], 0.6)

    def test_model_dir_inspection_reports_missing_files(self):
        info = inspect_model_dir(ROOT / "kc_saved_model")

        self.assertIn("ready", info)
        self.assertIn("missing", info)

    def test_emotion_domain_eval_builds_error_template(self):
        rows = read_domain_eval(ROOT / "data" / "sample_emotion_domain_eval.csv")
        template = build_error_template(rows)

        self.assertEqual(len(rows), 60)
        self.assertEqual(template[0]["true_label"], rows[0]["stage2"])
        self.assertEqual(template[0]["pred_label"], "")

    def test_emotion_error_summary_counts_confusion(self):
        rows = [
            {"text": "a", "true_label": "기쁨", "pred_label": "기쁨", "score": "0.9", "error_type": "", "memo": ""},
            {"text": "b", "true_label": "놀람", "pred_label": "기쁨", "score": "0.8", "error_type": "surprise_valence", "memo": "mixed"},
            {"text": "c", "true_label": "불안", "pred_label": "", "score": "", "error_type": "", "memo": ""},
        ]

        summary = summarize_errors(rows)

        self.assertEqual(summary["totalRows"], 3)
        self.assertEqual(summary["evaluatedRows"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["errorTypes"], {"surprise_valence": 1})

    def test_top_n_zero_returns_empty_result(self):
        result = recommend_top_n(
            user_id=7,
            candidate_places=[place(1, "park", "공원")],
            recent_emotion_idx=None,
            recent_emotion_score=0.0,
            fav_categories={},
            scrap_place_ids=set(),
            place_positive_ratio={},
            followed_positive_count={},
            top_n=0,
        )
        self.assertEqual(result, [])

    def test_backend_sample_payload_can_be_recommended(self):
        payload_path = ROOT / "dev" / "sample_payloads" / "reco_req_backend.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        result = recommend_from_payload(payload)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["placeId"], 610)
        self.assertIn("reason", result[0])

    def test_low_confidence_recent_emotion_is_parsed_as_unreliable(self):
        parsed = parse_request({
            "userId": 7,
            "context": {
                "recentEmotion": {
                    "emotionLabel": LABELS[0],
                    "emotionScore": 0.41,
                    "safeLabel": "unknown",
                    "isReliable": False,
                }
            },
            "candidates": [place(1, "park", "park").__dict__],
        })

        self.assertIsNone(parsed["recent_idx"])
        self.assertEqual(parsed["recent_score"], 0.0)
        self.assertFalse(parsed["recent_reliable"])

    def test_unreliable_emotion_reduces_emotion_weight(self):
        result = recommend_top_n(
            user_id=7,
            candidate_places=[place(1, "park", "park")],
            recent_emotion_idx=to_label_idx(LABELS[0]),
            recent_emotion_score=0.9,
            fav_categories={},
            scrap_place_ids=set(),
            place_positive_ratio={1: 0.5},
            followed_positive_count={},
            top_n=1,
            debug=True,
            recent_emotion_reliable=False,
        )

        self.assertEqual(result[0]["reason"]["emotion_reliable"], 0.0)
        self.assertLess(result[0]["reason"]["w_emo"], 0.25)

    def test_policy_scenarios_match_expected_top_place(self):
        payload_path = ROOT / "dev" / "sample_payloads" / "reco_policy_scenarios.json"
        scenarios = json.loads(payload_path.read_text(encoding="utf-8"))

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                result = recommend_from_payload(scenario["request"])
                self.assertEqual(result[0]["placeId"], scenario["expectedTopPlaceId"])

    def test_recommender_evaluation_sample_metrics(self):
        payload_path = ROOT / "dev" / "sample_payloads" / "reco_eval_cases.json"
        result = evaluate_cases(load_cases(payload_path), k=3)

        self.assertEqual(result["caseCount"], 3)
        self.assertIn("precision@3", result["aggregate"])
        self.assertIn("ndcg@3", result["aggregate"])
        self.assertGreaterEqual(result["aggregate"]["hitRate@3"], 1.0)
        self.assertGreater(result["aggregate"]["mrr@3"], 0.0)

    def test_low_confidence_emotion_result_keeps_original_label_but_marks_safe_label_unknown(self):
        result = build_emotion_result(17, LABELS[0], 0.41)

        self.assertEqual(result["emotionLabel"], LABELS[0])
        self.assertEqual(result["safeLabel"], UNKNOWN_LABEL)
        self.assertFalse(result["isReliable"])
        self.assertFalse(is_reliable_prediction(0.41))

    def test_high_confidence_emotion_result_is_reliable(self):
        result = build_emotion_result(17, LABELS[0], 0.87)

        self.assertEqual(result["safeLabel"], LABELS[0])
        self.assertTrue(result["isReliable"])
        self.assertTrue(is_reliable_prediction(0.87))

    def test_interaction_logs_can_be_converted_to_eval_cases(self):
        payload_path = ROOT / "dev" / "sample_payloads" / "reco_interaction_logs_sample.json"
        cases = build_cases(load_logs(payload_path))
        result = evaluate_cases(cases, k=3)

        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["gradedRelevance"]["501"], 2.0)
        self.assertEqual(cases[1]["gradedRelevance"]["610"], 3.0)
        self.assertEqual(result["caseCount"], 2)
        self.assertEqual(result["aggregate"]["hitRate@3"], 1.0)

    def test_insight_single_log_gives_light_advice_without_pattern_claim(self):
        evidence = assess_evidence([
            {"label": "불안", "category": "사무실"},
        ])
        advice = build_light_advice(evidence)

        self.assertEqual(evidence.confidence, "light")
        self.assertFalse(evidence.can_make_pattern_claim)
        self.assertFalse(evidence.can_make_place_claim)
        self.assertIn("경향을 단정", advice)

    def test_insight_request_aliases_are_parsed_without_mq(self):
        req = parse_insight_request({
            "requestId": "insight-1",
            "user_id": "12",
            "logs": [
                {"emotionLabel": "기쁨", "placeCat": "공원", "name": "서울숲"},
            ],
        })

        self.assertEqual(req.user_id, 12)
        self.assertEqual(req.request_id, "insight-1")
        self.assertEqual(req.logs[0]["label"], "기쁨")
        self.assertEqual(req.logs[0]["category"], "공원")
        self.assertEqual(req.logs[0]["placeName"], "서울숲")

    def test_insight_place_signal_requires_repeated_category(self):
        logs = [
            {"label": "기쁨", "category": "공원"},
            {"label": "불안", "category": "사무실"},
            {"label": "놀람", "category": "카페"},
        ]
        evidence = assess_evidence(logs)

        self.assertEqual(evidence.confidence, "limited")
        self.assertTrue(evidence.can_make_pattern_claim)
        self.assertFalse(evidence.can_make_place_claim)
        self.assertEqual(place_valences(logs), [])

    def test_insight_repeated_category_can_make_place_claim(self):
        logs = [
            {"label": "기쁨", "category": "공원"},
            {"label": "기쁨", "category": "공원"},
            {"label": "불안", "category": "사무실"},
        ]
        evidence = assess_evidence(logs)
        advice = build_light_advice(evidence)

        self.assertTrue(evidence.can_make_place_claim)
        self.assertEqual(evidence.place_valences[0].placeCat, "공원")
        self.assertEqual(evidence.place_valences[0].count, 2)
        self.assertIn("공원", advice)

    def test_domain_eval_sample_is_balanced_by_label(self):
        rows = read_domain_eval(ROOT / "data" / "sample_emotion_domain_eval.csv")
        counts = {label: 0 for label in LABELS}
        for row in rows:
            counts[row["stage2"]] += 1

        self.assertEqual(len(rows), 60)
        self.assertEqual(set(counts.values()), {10})

    def test_emotion_domain_metrics_and_threshold_report(self):
        rows = [
            {"true": "기쁨", "pred": "기쁨", "score": 0.91},
            {"true": "슬픔", "pred": "불안", "score": 0.72},
            {"true": "불안", "pred": "불안", "score": 0.42},
        ]

        metrics = metrics_for(rows)
        thresholds = threshold_report(rows, [0.7])

        self.assertEqual(metrics["caseCount"], 3)
        self.assertEqual(metrics["correct"], 2)
        self.assertEqual(thresholds[0]["accepted"], 2)
        self.assertEqual(thresholds[0]["rejected"], 1)
        self.assertEqual(thresholds[0]["rejectedErrors"], 0)

    def test_emotion_data_audit_summarizes_basic_quality_signals(self):
        rows = [
            {"text": "오늘은 기분이 좋았다.", "stage1": "긍정", "stage2": "기쁨", "persona": "직장인"},
            {"text": "내일 발표가 걱정돼서 불안했다.", "stage1": "부정", "stage2": "불안", "persona": "대학생"},
            {"text": "내일 발표가 걱정돼서 불안했다.", "stage1": "부정", "stage2": "불안", "persona": "대학생"},
        ]

        result = analyze_rows(rows)

        self.assertEqual(result["rowCount"], 3)
        self.assertEqual(result["blankText"], 0)
        self.assertEqual(result["exactDuplicateExtraRows"], 1)
        self.assertEqual(result["sameTextDifferentLabels"], 0)
        self.assertEqual(result["labelCounts"]["불안"], 2)

    def test_prepare_emotion_dataset_removes_duplicates_before_split(self):
        rows = []
        for label in [LABELS[0], LABELS[3]]:
            for idx in range(10):
                rows.append({"text": f"{label} sample {idx}", "stage1": "긍정", "stage2": label, "persona": "tester"})
        rows.append({"text": f"{LABELS[0]} sample 0", "stage1": "긍정", "stage2": LABELS[0], "persona": "tester"})

        cleaned, clean_report = clean_rows(rows)
        splits, split_report = stratified_split(cleaned, seed="test")

        self.assertEqual(clean_report["removedDuplicateRows"], 1)
        self.assertEqual(len(cleaned), 20)
        self.assertEqual(split_report["exactLeakage"]["trainTest"], 0)
        self.assertEqual(sum(len(values) for values in splits.values()), 20)

    def test_boundary_case_builder_focuses_on_target_label_errors_and_low_confidence(self):
        rows = [
            {"text": "a", "true": LABELS[5], "pred": LABELS[3], "score": "0.91", "isCorrect": "False"},
            {"text": "b", "true": LABELS[4], "pred": LABELS[4], "score": "0.62", "isCorrect": "True"},
            {"text": "c", "true": LABELS[0], "pred": LABELS[0], "score": "0.99", "isCorrect": "True"},
        ]

        cases = build_boundary_cases(rows, target_labels=[LABELS[3], LABELS[4], LABELS[5]], threshold=0.7)

        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["reason"], "wrong_prediction")
        self.assertEqual(cases[1]["reason"], "low_confidence")

    def test_boundary_review_uses_review_label_as_effective_truth(self):
        rows = [
            {"text": "a", "true_label": LABELS[4], "pred_label": LABELS[5], "score": "0.8", "review_label": LABELS[5], "secondary_label": LABELS[4]},
            {"text": "b", "true_label": LABELS[3], "pred_label": LABELS[3], "score": "0.9", "review_label": "", "secondary_label": ""},
        ]

        report = evaluate_review(rows)

        self.assertEqual(report["reviewedLabelCount"], 1)
        self.assertEqual(report["correctionCount"], 1)
        self.assertEqual(report["secondaryLabelCount"], 1)
        self.assertEqual(report["originalMetrics"]["correct"], 1)
        self.assertEqual(report["reviewedMetrics"]["correct"], 2)


if __name__ == "__main__":
    unittest.main()
