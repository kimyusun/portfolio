# 감정 분석 Worker

## 모델 파일이 필요한 경우

감정 분석 모델 본체는 실제 추론을 할 때 필요합니다.

필요한 작업:

- `ai.infra.mq_emotion`의 `run_emotion_worker` 실행
- `analyze_emotion_text()`로 실제 문장 감정 추론
- `dev/smoke_tests/selftest_emotion.py` 실행
- `scripts/evaluate_emotion.py`로 실제 모델 성능 평가

이 작업들은 로컬 HuggingFace 모델 디렉터리가 필요합니다. 모델 경로는 `.env`의 `EMO_MODEL_DIR`로 지정합니다.

## 모델 파일 없이 가능한 작업

모델 본체가 없어도 다음 작업은 가능합니다.

- 감정 라벨 정책 검토
- 감정 요청 payload 형식 문서화
- 추천 로직에서 감정 라벨을 어떻게 해석하는지 테스트
- 모델 파일 공개 제외 정책 검토
- 감정 모델 개선 계획 수립

즉, 포트폴리오 정리와 설계 개선은 모델 없이도 진행할 수 있지만, 실제 추론 결과와 성능 수치는 모델 파일이 있어야 확인할 수 있습니다.

## Emotion Request Schema

감정 분석 worker는 다음 필드를 받습니다.

```json
{
  "memo_id": 123,
  "content": "오늘 공원 산책이 좋았다"
}
```

호환을 위해 다음 alias도 허용합니다.

| canonical | aliases |
| --- | --- |
| `memo_id` | `memoId`, `id` |
| `content` | `text`, `body` |

## Emotion Result

감정 분석 결과는 백엔드 DB의 `EmotionEntity`에 저장되는 흐름을 기준으로 합니다.

| field | meaning |
| --- | --- |
| `memo_id` | 감정 분석 대상 메모 id |
| `emotion_label` | 예측 감정 라벨 |
| `emotion_score` | 모델 confidence score |

현재 라벨은 다음 6개입니다.

```text
기쁨 / 놀람 / 분노 / 불안 / 상처 / 슬픔
```

라벨 정책은 `ai/emotion_policy.py`에서 관리합니다.

## Self Test

모델 파일이 있는 환경에서는 다음 명령으로 모델 로딩과 단일 문장 추론을 확인합니다.

```bash
python dev/smoke_tests/selftest_emotion.py --text "오늘 공원 산책이 좋았다"
```

모델 경로를 직접 지정할 수도 있습니다.

```bash
python dev/smoke_tests/selftest_emotion.py --model-dir kc_saved_model --text "오늘 공원 산책이 좋았다"
```

## Evaluation

실제 평가 데이터와 모델 파일이 있는 경우 다음 명령으로 평가 리포트를 생성합니다.

```bash
python scripts/evaluate_emotion.py
```

환경 변수:

| env | meaning |
| --- | --- |
| `EMO_MODEL_DIR` | 로컬 HuggingFace 모델 디렉터리 |
| `EMOTION_DATA_CSV` | 평가용 CSV 파일 경로 |

평가 CSV는 최소한 다음 컬럼이 필요합니다.

```text
text, stage2
```

## 포트폴리오 설명 문장

> 감정 분석 worker는 실제 추론에는 로컬 HuggingFace 모델 파일이 필요하지만, 포트폴리오 정리 단계에서는 모델 본체를 공개 저장소에 포함하지 않고 `.env`의 `EMO_MODEL_DIR`로 분리했다. 대신 감정 라벨 정책, 요청/응답 형식, 평가 스크립트, 모델 개선 계획을 문서화해 모델 파일이 없어도 구조와 판단 근거를 확인할 수 있게 했다.

## CPU 모델 로드 스모크와 성능 확인

모델 학습이나 대규모 평가는 Colab/GPU가 현실적이지만, 공개 전 검증 단계에서 다음 작업은 CPU로도 가능합니다.

- 로컬 모델 디렉터리가 올바른지 확인
- tokenizer/model weight 로드 확인
- 단일 문장 추론 확인
- 짧은 샘플 문장 기준 warm inference 시간 측정

실행 예시:

```bash
python dev/smoke_tests/selftest_emotion.py --model-dir kc_saved_model --text "오늘 공원 산책이 좋았어"
python scripts/benchmark_emotion_model.py --model-dir kc_saved_model --loops 20
```

Windows 한글 경로/출력 문제가 있으면 다음처럼 UTF-8 출력을 고정할 수 있습니다.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python dev\smoke_tests\selftest_emotion.py --model-dir kc_saved_model --text "오늘 공원 산책이 좋았어"
```

현재 로컬 CPU 기준 스모크 결과:

- device: `cpu`
- torch: `2.12.0+cpu`
- transformers: `5.9.0`
- model load: 약 `0.54s`
- warm inference average: 약 `45ms`
- p95 inference: 약 `79ms`

이 수치는 실제 운영 성능 보장이 아니라, 현재 공개 전 환경에서 모델 파일이 로드되고 추론 경로가 동작한다는 스모크 검증입니다. 실제 서비스 성능은 MQ 왕복, DB 저장, 동시 처리량, 서버 CPU/GPU 사양을 포함해 별도로 측정해야 합니다.