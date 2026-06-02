# 감정 라벨 경계 검토 기록

## 목적

`슬픔/불안/상처`는 실제 감정 경험에서 자주 함께 나타납니다. 단일 라벨 분류 모델에서는 이 복합 감정을 하나의 primary label로 정해야 하므로, 모델 오답만 보고 바로 학습 데이터를 늘리기보다 사람이 라벨 경계를 먼저 검토했습니다.

검토 파일:

```text
data/emotion_boundary_review_template.xlsx
```

이 파일은 로컬 검토용이며 GitHub에 올리지 않습니다.

## 검토 기준

- `상처`: 감정의 원인이 타인의 말, 행동, 관계적 거절, 무시, 비교, 배신에 있을 때
- `슬픔`: 상실감, 외로움, 허전함, 우울감처럼 감정의 중심이 내면의 침잠에 있을 때
- `불안`: 아직 일어나지 않은 일, 불확실성, 걱정, 긴장, 위험 예측이 중심일 때

복합 감정이 있는 경우 `review_label`에는 primary label을, `secondary_label`에는 함께 느껴지는 보조 감정을 기록했습니다.

## 2026-06-01 검토 결과

| item | count |
| --- | ---: |
| boundary candidate rows | 54 |
| rows with review_label | 18 |
| actual label corrections | 17 |
| rows with secondary_label | 15 |

라벨 변경 방향:

| change | count |
| --- | ---: |
| 상처 -> 슬픔 | 7 |
| 슬픔 -> 불안 | 4 |
| 슬픔 -> 상처 | 2 |
| 불안 -> 슬픔 | 2 |
| 분노 -> 상처 | 1 |
| 불안 -> 상처 | 1 |

secondary label 조합:

| pair | count |
| --- | ---: |
| 불안 + 슬픔 | 4 |
| 슬픔 + 불안 | 4 |
| 슬픔 + 상처 | 3 |
| 상처 + 슬픔 | 2 |
| 상처 + 분노 | 1 |
| 상처 + 불안 | 1 |

## boundary 후보셋 재평가

검토 전후를 같은 54개 boundary 후보셋에서 비교했습니다.

| metric | original label | reviewed label |
| --- | ---: | ---: |
| accuracy | 0.4815 | 0.7407 |
| present-label macro F1 | 0.3053 | 0.5369 |

`present-label macro F1`은 이 후보셋에 실제로 등장한 `분노/불안/상처/슬픔`만 대상으로 계산한 값입니다. 후보셋 자체가 오답/낮은 confidence 중심으로 뽑힌 어려운 사례이므로 전체 모델 성능이 아니라 라벨 경계 품질 확인용으로 해석해야 합니다.

## 해석

검토 결과는 모델이 무조건 틀렸다는 의미가 아닙니다. 오히려 기존 정답 라벨 자체가 단일 라벨로 자르기 어려운 사례를 포함하고 있었음을 보여줍니다.

특히 `상처 -> 슬픔` 변경이 많았다는 점은, 관계적 사건이 있더라도 문장의 중심이 타인의 가해보다 내면의 허전함과 침잠에 가까운 경우가 있었다는 뜻입니다.

따라서 다음 개선 방향은 단순히 모델을 다시 학습시키는 것이 아니라 다음 순서가 적절합니다.

1. primary/secondary label 기준을 문서화합니다.
2. `review_label`이 있는 행을 라벨 correction 후보로 관리합니다.
3. `secondary_label`이 있는 행은 단일 라벨 모델의 한계 사례로 따로 기록합니다.
4. 추가 학습을 한다면 변경 라벨을 train에 바로 섞기 전에, boundary evaluation set을 따로 유지합니다.

## 포트폴리오 설명 문장

> 감정은 실제로 복합적이기 때문에 `상처/슬픔/불안`처럼 경계가 겹치는 라벨은 모델 오답만으로 판단하기 어렵다고 보았습니다. 그래서 오답과 낮은 confidence 사례를 사람이 다시 검토해 primary label과 secondary label을 분리했고, 일부 기존 정답 라벨 자체도 조정했습니다. 이 과정을 통해 단일 라벨 감정 분류의 한계를 인지하고, 향후 multi-label 또는 primary-secondary emotion 구조로 확장할 근거를 마련했습니다.
