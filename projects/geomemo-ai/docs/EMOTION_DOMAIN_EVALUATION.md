# 감정 도메인 평가셋과 에러 분석

## 목적

모델 업그레이드 여부를 판단하려면 실제 GeoMemo 도메인에 가까운 문장에서 모델이 무엇을 잘 맞히고 무엇을 헷갈리는지 확인해야 합니다.

현재 모델의 기존 평가 결과는 baseline으로 사용할 수 있지만, GeoMemo는 짧은 일기형 메모를 다루므로 별도의 도메인 평가셋과 에러 분석이 필요합니다.
현재 모델은 GPT로 생성한 합성 데이터를 학습에 활용했기 때문에, 기존 평가 점수가 높더라도 실제 사용자 메모에 대한 일반화 성능은 별도로 검증해야 합니다. 이 문서의 목적은 그 검증을 위한 최소 평가셋과 에러 분석 흐름을 만드는 것입니다.

## 샘플 도메인 평가셋

샘플 파일:

```text
data/sample_emotion_domain_eval.csv
```

컬럼:

| column | meaning |
| --- | --- |
| `text` | 평가할 메모 문장 |
| `stage1` | 긍정/부정 상위 라벨 |
| `stage2` | 6개 감정 라벨 |
| `persona` | 예시 사용자 맥락 |
| `note` | 문장 설계 의도 |

현재 샘플은 각 라벨당 10개씩, 총 60개 문장으로 구성했습니다. 명시적인 감정 표현뿐 아니라 완곡한 표현, 장소 맥락, 혼합 감정, 애매한 문장을 섞었습니다. 이 파일은 실제 성능을 증명하기 위한 데이터가 아니라, 합성 학습 데이터와 독립적인 도메인 평가셋을 어떻게 만들지 보여주는 샘플입니다.

## 에러 분석 템플릿 만들기

모델 예측 결과를 사람이 검토하기 위한 템플릿을 생성합니다.

```bash
python scripts/build_emotion_error_template.py --input data/sample_emotion_domain_eval.csv --out data/emotion_error_analysis_template.csv
```

생성되는 컬럼:

| column | meaning |
| --- | --- |
| `text` | 입력 문장 |
| `true_label` | 사람이 붙인 정답 라벨 |
| `pred_label` | 모델 예측 라벨 |
| `score` | confidence score |
| `error_type` | 오류 유형 |
| `memo` | 개선 메모 |

## 오류 유형 예시

| error_type | meaning |
| --- | --- |
| `label_confusion` | 서로 가까운 라벨을 혼동함 |
| `context_missing` | 짧은 문장이라 맥락이 부족함 |
| `sarcasm` | 반어/비꼼 표현을 잘못 해석함 |
| `mixed_emotion` | 한 문장에 여러 감정이 섞임 |
| `surprise_valence` | `놀람`의 긍정/부정 방향을 잘못 해석함 |
| `low_confidence` | confidence가 낮아 판단이 불안정함 |

## 에러 분석 요약하기

예측값과 오류 유형을 채운 뒤 다음 명령으로 요약할 수 있습니다.

```bash
python scripts/analyze_emotion_errors.py --input data/emotion_error_analysis_template.csv
```

요약 결과에는 다음 항목이 포함됩니다.

- 전체 row 수
- 예측값이 채워진 row 수
- accuracy
- true label 분포
- pred label 분포
- confusion pair
- error type 분포
- error type별 예시 문장

## 실제 모델 도메인 스모크 평가

현재 로컬에 보관된 `kc_saved_model/` 모델을 CPU로 직접 로드해 샘플 도메인 평가셋을 검증할 수 있습니다.

```bash
python scripts/evaluate_emotion_domain_model.py --model-dir kc_saved_model --input data/sample_emotion_domain_eval.csv
```

2026-05-28 기준 샘플 60개 평가 결과:

| metric | value |
| --- | ---: |
| case count | 60 |
| accuracy | 0.8833 |
| macro F1 | 0.8846 |
| model load | 0.5131s |
| avg inference | 43.0291ms |
| p95 inference | 62.4177ms |
| device | cpu |

확인된 오류와 주의점:

- `슬픔 -> 불안` 혼동이 2건, `슬픔 -> 상처` 혼동이 1건 있었습니다. `슬픔` recall은 0.70으로 가장 낮았습니다.
- `불안`은 recall은 0.90이지만 precision이 0.6923으로 낮았습니다. 다른 부정 감정 일부를 `불안`으로 끌어오는 경향이 있습니다.
- confidence 0.6 미만인 예측은 5건이었습니다. 다만 높은 confidence 오답도 있어 confidence threshold만으로 오류를 모두 걸러내기는 어렵습니다.
- threshold 0.7을 적용하면 coverage는 0.8333, accepted accuracy는 0.92까지 올라갔습니다. 추천/인사이트에서 낮은 confidence 감정을 약하게 반영하는 정책은 유효하지만, 모델 자체의 라벨 혼동을 완전히 해결하지는 못합니다.
- 이 결과는 60개 샘플에 대한 예비 도메인 평가입니다. 실제 성능 증명으로 사용하면 안 됩니다. 포트폴리오에서는 "합성데이터 기반 모델의 한계를 인지하고, 도메인 샘플 평가와 confidence 정책으로 검증 체계를 보강했으며, `슬픔/불안` 혼동을 다음 개선 대상으로 식별했다"는 근거로 설명하는 편이 적절합니다.

## 해석 방법

이 분석은 단순히 정확도를 보기 위한 것이 아닙니다. 더 중요한 질문은 다음입니다.

- 어떤 라벨이 자주 헷갈리는가?
- `놀람`은 긍정/중립/부정 문맥에서 어떻게 흔들리는가?
- confidence가 높은 오답이 있는가?
- 추천이나 인사이트에 영향을 줄 정도의 오류가 있는가?
- 정책 개선으로 충분한가, fine-tuning이 필요한가?

## 모델 업그레이드 판단 기준

다음이 확인되면 모델 업그레이드를 검토합니다.

- 특정 라벨의 F1이 반복적으로 낮다.
- `불안`/`상처`/`슬픔`처럼 서비스 대응이 달라질 수 있는 라벨을 자주 혼동한다.
- `놀람`을 부정 문맥에서도 강한 긍정처럼 예측한다.
- confidence가 높은데 틀리는 경우가 많다.
- 정책 보정만으로 사용자 경험 리스크를 줄이기 어렵다.

## 포트폴리오 설명 문장

> 모델을 바로 교체하기보다, GeoMemo 도메인에 맞는 작은 평가셋과 에러 분석 표를 먼저 설계했다. 이를 통해 현재 모델을 baseline으로 두고 라벨 혼동, 문맥 부족, `놀람`의 valence 문제, confidence 문제를 확인한 뒤 fine-tuning이나 후보 모델 비교가 필요한지 판단할 수 있게 했다.
