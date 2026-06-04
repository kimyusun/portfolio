# MQ 메시지 계약

## 목적

GeoMemo-AI는 백엔드와 직접 함수 호출로 연결되지 않고 MQ 메시지를 통해 작업을 받습니다. 이 문서는 포트폴리오 공개용으로 각 queue/exchange의 payload 계약을 정리합니다.

실제 운영 환경의 MQ URL, DB URL, credential은 `.env`에만 둡니다. 공개 저장소에는 메시지 구조와 샘플만 남깁니다.

## 전체 흐름

```text
Backend API -> reco.req -> Recommender Worker -> reco.res -> Backend API
Backend API -> emotion.req -> Emotion Worker -> EmotionEntity
Backend API -> insight.req -> Insight Worker -> InsightEntity
Backend Domain Events -> geomemo.events -> Event Cache Consumer
```

## `reco.req`

장소 추천 요청입니다. 백엔드가 후보 장소와 사용자 컨텍스트를 보내면 AI worker가 점수를 계산합니다.

필수 필드:

| field | type | 설명 |
| --- | --- | --- |
| `userId` | number | 추천 대상 사용자 id |
| `candidates` | array | 추천 후보 장소 목록 |

선택 필드:

| field | type | 설명 |
| --- | --- | --- |
| `requestId` | string | 요청 추적 id |
| `top` | number | 반환할 추천 개수, 기본 5 |
| `debug` | boolean | 점수 근거 포함 여부 |
| `context.recentEmotion` | object or array | 최근 감정 정보 |
| `context.favCategories` | object | 사용자 선호 카테고리 count map |
| `context.scrapPlaceIds` | array | 사용자가 스크랩한 장소 id 목록 |
| `context.placeSignals` | array | 장소별 긍정 비율과 소셜 신호 |

`recentEmotion`은 기존 형식과 개선된 신뢰도 형식을 모두 받을 수 있습니다.

```json
{
  "label": "불안",
  "score": 0.92
}
```

```json
{
  "emotionLabel": "불안",
  "emotionScore": 0.41,
  "safeLabel": "unknown",
  "isReliable": false,
  "confidenceThreshold": 0.6
}
```

`safeLabel = unknown` 또는 `isReliable = false`이면 추천 worker는 감정 가중치를 낮추고, 장소 긍정 비율/카테고리/스크랩/소셜 신호를 더 크게 반영합니다.

## `reco.res`

추천 결과 응답입니다.

성공 응답:

```json
{
  "requestId": "req-backend-001",
  "userId": 12,
  "status": "ok",
  "items": [
    {
      "placeId": 610,
      "name": "조용한 카페",
      "category": "카페",
      "latitude": 37.5501,
      "longitude": 127.14,
      "score": 0.99
    }
  ],
  "meta": {
    "model": "reco-v1.1",
    "elapsedMs": 12
  }
}
```

실패 응답:

```json
{
  "requestId": "req-backend-001",
  "userId": 12,
  "status": "error",
  "error": "ValueError: ...",
  "meta": {"model": "reco-v1.1"}
}
```

## `emotion.req`

메모 감정 분석 요청입니다.

지원하는 입력 alias:

| 의미 | 지원 필드 |
| --- | --- |
| 메모 id | `memo_id`, `memoId`, `id` |
| 메모 본문 | `content`, `text`, `body` |
| 요청 id | `requestId`, `request_id` |

예시:

```json
{
  "memoId": 17,
  "text": "오늘 공원 산책이 좋았어"
}
```

worker 내부 결과 포맷:

```json
{
  "memoId": 17,
  "emotionLabel": "기쁨",
  "emotionScore": 0.87,
  "stage1": "긍정",
  "valence": 1.0,
  "safeLabel": "기쁨",
  "isReliable": true,
  "confidenceThreshold": 0.6
}
```

현재 DB 저장은 기존 schema 호환을 위해 `emotion_label`, `emotion_score` 중심으로 유지합니다. `safeLabel`과 `isReliable`은 추천/인사이트 정책으로 확장하기 위한 안전 필드입니다.

## `insight.req`

주간 인사이트 생성 요청입니다.

필수 필드:

| field | type | 설명 |
| --- | --- | --- |
| `userId` 또는 `user_id` | number | 인사이트 대상 사용자 id |
| `logs` | array | 주간 감정 로그 목록 |

로그 item alias:

| 의미 | 지원 필드 |
| --- | --- |
| 감정 라벨 | `label`, `emotionLabel` |
| 장소 카테고리 | `category`, `placeCat` |
| 장소 이름 | `placeName`, `name` |
| 감정 score | `score`, `emotionScore` |

예시:

```json
{
  "userId": 12,
  "logs": [
    {"label": "기쁨", "category": "공원", "placeName": "서울숲"},
    {"label": "불안", "category": "사무실", "placeName": "HQ-3F"}
  ]
}
```

인사이트 worker는 로그 수에 따라 근거 수준을 나눕니다.

| 기준 | 동작 |
| --- | --- |
| 감정 로그 0건 | 기록 유도 안내만 제공 |
| 감정 로그 1-2건 | 가벼운 컨디션 조언만 제공 |
| 감정 로그 3-4건 | 제한적 경향만 표현 |
| 감정 로그 5건 이상 | 주간 경향 요약 가능 |
| 같은 장소 카테고리 2건 이상 | 장소별 경향 언급 가능 |

## `geomemo.events`

추천 worker가 빠르게 참조할 수 있는 인메모리 캐시를 업데이트하기 위한 domain event exchange입니다.

지원 routing key:

| routing key | 목적 |
| --- | --- |
| `location.upsert` | 장소 카테고리/이름 캐시 업데이트 |
| `memo.upsert` | 공개 메모의 감정/장소/작성자 신호 반영 |
| `memo.delete` | 삭제된 메모 신호 제거 |
| `scrap.event` | 사용자 스크랩 신호 반영 |
| `follow.event` | 팔로잉 관계 신호 반영 |

예시:

```json
{
  "memo_id": 1001,
  "user_id": 12,
  "location_id": 610,
  "is_public": true,
  "emotion_label": "기쁨",
  "emotion_score": 0.87,
  "category": "카페",
  "createdAt": "2026-05-28T10:00:00+09:00"
}
```

## 테스트 가능한 경계

현재 repo에서는 실제 MQ/DB 없이 다음 경계를 테스트합니다.

- 추천 요청 parsing: `ai/recommender/request_parser.py`
- 추천 점수 계산: `ai/recommender/recommender.py`
- 감정 요청 parsing과 결과 포맷: `ai/infra/emotion_message.py`
- 인사이트 요청 parsing: `ai/infra/insight_message.py`
- 인사이트 근거 수준 판단: `ai/infra/insight_policy.py`

이 구조 덕분에 팀 프로젝트의 인프라가 없어도 핵심 AI 정책을 단위 테스트로 검증할 수 있습니다.
