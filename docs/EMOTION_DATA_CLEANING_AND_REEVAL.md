# 감정 데이터 정제와 재평가 기록

## 목적

원본 합성 학습 데이터가 baseline 학습에 충분했는지 확인한 뒤, 다음 단계로 중복 제거, 누수 방지 split, cleaned 기준 재평가, 취약 라벨 보강 후보 추출을 진행했습니다.

원본과 파생 CSV는 모두 로컬 분석용이며 GitHub에 올리지 않습니다.

## 1. 중복 제거

실행 명령:

```bash
python scripts/prepare_emotion_dataset.py --input data/emotion_data.csv
```

결과:

| item | count |
| --- | ---: |
| input rows | 3,940 |
| cleaned rows | 3,843 |
| removed duplicate rows | 97 |
| same text different labels | 0 |

cleaned 라벨 분포:

| label | count |
| --- | ---: |
| 상처 | 748 |
| 놀람 | 712 |
| 기쁨 | 636 |
| 불안 | 633 |
| 슬픔 | 606 |
| 분노 | 508 |

## 2. 누수 방지 split

중복 제거 후 text 기준으로 deterministic stratified split을 만들었습니다.

| split | count |
| --- | ---: |
| train | 3,074 |
| val | 385 |
| test | 384 |

exact text leakage:

| pair | count |
| --- | ---: |
| train-val | 0 |
| train-test | 0 |
| val-test | 0 |

## 3. cleaned test 기준 재평가

실행 명령:

```bash
python scripts/evaluate_emotion_domain_model.py --model-dir kc_saved_model --input data/emotion_test.csv --predictions-out reports/emotion_cleaned_test_predictions.csv --errors-out reports/emotion_cleaned_test_errors.csv --summary-out reports/emotion_cleaned_test_summary.json --compact
```

결과:

| metric | value |
| --- | ---: |
| test rows | 384 |
| accuracy | 0.8828 |
| macro F1 | 0.8856 |
| error count | 45 |
| low confidence count | 29 |
| avg inference | 62.6097ms |
| p95 inference | 96.3404ms |

라벨별 결과:

| label | precision | recall | F1 | support |
| --- | ---: | ---: | ---: | ---: |
| 기쁨 | 0.9107 | 0.8095 | 0.8571 | 63 |
| 놀람 | 0.8462 | 0.9296 | 0.8859 | 71 |
| 분노 | 1.0000 | 0.9608 | 0.9800 | 51 |
| 불안 | 0.8971 | 0.9531 | 0.9242 | 64 |
| 상처 | 0.8873 | 0.8400 | 0.8630 | 75 |
| 슬픔 | 0.7903 | 0.8167 | 0.8033 | 60 |

주요 confusion:

| confusion | count |
| --- | ---: |
| 기쁨 -> 놀람 | 12 |
| 상처 -> 슬픔 | 11 |
| 슬픔 -> 불안 | 6 |
| 놀람 -> 기쁨 | 5 |
| 슬픔 -> 상처 | 5 |

threshold 기준:

| threshold | coverage | accepted accuracy |
| --- | ---: | ---: |
| 0.6 | 0.9245 | 0.9014 |
| 0.7 | 0.8542 | 0.9207 |
| 0.8 | 0.6615 | 0.9646 |

## 4. 부족 라벨 보강 후보

실행 명령:

```bash
python scripts/build_emotion_boundary_cases.py --predictions reports/emotion_cleaned_test_predictions.csv --out data/emotion_boundary_candidates.csv --target-labels 슬픔,불안,상처 --threshold 0.7
```

결과:

- `슬픔/불안/상처` 관련 오답 또는 낮은 confidence 사례 54개를 추출했습니다.
- 이 CSV는 사람이 다시 읽고 라벨 경계, 문장 맥락, 보강 필요 여부를 검토하기 위한 로컬 작업 파일입니다.

## 현재 판단

중복 제거와 누수 방지 split을 적용해도 cleaned test 성능은 Accuracy `0.8828`, Macro-F1 `0.8856`으로 유지되었습니다. 따라서 모델은 포트폴리오 baseline으로는 유지할 수 있습니다.

다만 이 평가는 여전히 원본 합성 데이터에서 만든 split 기준입니다. 실제 사용자 메모에 대한 일반화 성능을 보장하지는 않습니다.

현재 가장 좋은 개선 방향은 다음 순서입니다.

1. `data/emotion_boundary_candidates.csv`를 사람이 검토합니다.
2. `슬픔/불안/상처` 경계 문장을 추가로 수집하거나 직접 작성합니다.
3. 실제 메모와 더 가까운 짧은 문장, 오타, 이모티콘, 혼합 감정 문장을 평가셋에 보강합니다.
4. 그 다음 targeted fine-tuning 또는 후보 모델 비교를 진행합니다.

## 포트폴리오 설명 문장

> 원본 합성 데이터는 baseline fine-tuning에는 사용할 수 있는 규모였지만, 중복과 합성 문장 패턴으로 인해 평가 점수가 부풀 가능성이 있었습니다. 그래서 원본 데이터를 중복 제거하고, text 기준 누수가 없는 train/val/test split을 새로 만들었으며, cleaned test 기준으로 모델을 재평가했습니다. 그 결과 모델은 baseline으로 유지 가능하지만 `기쁨/놀람`, `상처/슬픔`, `슬픔/불안` 경계에서 혼동이 확인되어, 해당 라벨 경계 사례를 별도 보강 후보셋으로 추출했습니다.
