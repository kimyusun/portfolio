# 추천 로그 평가 데이터 스키마

## 목적

추천 로직을 실제로 개선하려면 추천 결과가 사용자 행동으로 이어졌는지 기록해야 합니다. 이 문서는 운영 로그가 생겼을 때 어떤 필드를 남기고, 그 로그를 어떻게 평가 데이터로 변환할지 정리합니다.

현재 프로젝트에는 실제 운영 로그가 없으므로 `dev/sample_payloads/reco_interaction_logs_sample.json`에 샘플 로그를 두었습니다. 이 샘플은 실제 성능 증명이 아니라 평가 파이프라인의 입력 형식을 보여주기 위한 데이터입니다.

## 로그 단위

추천 요청 1건을 하나의 로그 단위로 봅니다.

필수에 가까운 필드:

| field | meaning |
| --- | --- |
| `requestId` | 추천 요청 id |
| `userId` | 사용자 id |
| `createdAt` | 추천 요청 시각 |
| `shownPlaceIds` | 사용자에게 노출된 장소 id 순서 |
| `request` | 당시 추천 요청 payload 전체 |

후속 행동 필드:

| field | meaning | relevance |
| --- | --- | ---: |
| `detailViewedPlaceIds` | 장소 상세를 본 장소 | 0.5 |
| `clickedPlaceIds` | 추천 결과에서 클릭한 장소 | 1.0 |
| `scrappedPlaceIds` | 추천 후 스크랩한 장소 | 2.0 |
| `memoCreatedPlaceIds` | 추천 후 메모를 작성한 장소 | 3.0 |

점수는 절대적인 정답이 아니라 baseline label입니다. 실제 서비스에서는 팀의 목표에 맞춰 조정해야 합니다.

## 변환 흐름

```text
recommendation interaction logs
  -> scripts/build_recommender_eval_cases.py
  -> recommender eval cases
  -> scripts/evaluate_recommender.py
  -> Precision@K / MRR@K / NDCG@K
```

실행 예시:

```bash
python scripts/build_recommender_eval_cases.py --logs dev/sample_payloads/reco_interaction_logs_sample.json --out dev/sample_payloads/reco_eval_cases_from_logs.json
python scripts/evaluate_recommender.py --cases dev/sample_payloads/reco_eval_cases_from_logs.json --k 3
```

## 주의할 점

- 노출되지 않은 장소의 클릭/스크랩은 평가 대상에서 제외합니다.
- 클릭은 호기심일 수 있으므로 스크랩이나 메모 작성보다 낮은 relevance로 둡니다.
- 메모 작성은 GeoMemo 서비스의 핵심 행동에 가깝기 때문에 가장 높은 relevance로 둡니다.
- 사용자마다 행동 패턴이 다르므로 전체 평균만 보지 말고 감정 라벨, 신규/기존 사용자, 카테고리별로 나누어 봐야 합니다.

## 포트폴리오 설명 문장

> 추천 결과의 품질을 실제로 개선하기 위해 추천 노출 로그와 후속 행동 로그를 평가 데이터로 변환하는 구조를 설계했다. 클릭, 상세 조회, 스크랩, 메모 작성 같은 implicit feedback을 graded relevance로 바꾸고, 이를 NDCG@K, MRR@K 같은 랭킹 지표로 평가할 수 있게 했다. 현재는 샘플 로그 기반이지만, 실제 서비스 로그가 생기면 같은 파이프라인으로 가중치 조정이나 랭킹 모델 개선에 사용할 수 있다.
