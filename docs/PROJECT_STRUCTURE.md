# 프로젝트 구조

이 저장소는 실제 실행에 필요한 AI worker 코드와 개발 중 사용한 테스트/실험 파일을 분리해서 관리합니다.

## 실제 프로젝트 코드

- `run_all_workers.py`: 추천, 감정 분석, 인사이트, 이벤트 캐시 worker를 함께 실행하는 진입점입니다.
- `ai/emotion_policy.py`: 감정 라벨, index, 긍정/부정 stage, valence를 관리하는 공통 정책 모듈입니다.
- `ai/infra/`: MQ 연결, 이벤트 캐시 consumer, 감정 분석 worker, 주간 인사이트 worker가 들어 있습니다.
- `ai/recommender/`: 장소 추천 요청 스키마, 추천 점수 계산 로직, 추천 MQ worker가 들어 있습니다.
- `requirements.txt`: 프로젝트 실행에 필요한 Python 패키지 목록입니다.

## 개발 및 테스트용 파일

- `dev/smoke_tests/`: 감정 모델 파일과 로컬 추론 환경을 확인하는 self-test 스크립트입니다.
- `dev/sample_payloads/`: MQ 또는 API 연동 테스트에 사용하는 샘플 JSON payload입니다.
- `dev/mq_tools/`: RabbitMQ/Amazon MQ 메시지 publish, consume, roundtrip 확인용 개발 도구입니다.
- `scripts/`: 모델 평가와 추천 평가처럼 반복적으로 실행하는 유지보수/분석 스크립트입니다.
- `examples/`: 실제 운영 경로에는 포함하지 않는 예시 코드입니다.
- `tests/`: DB/MQ 없이 실행 가능한 추천 로직 단위 테스트입니다.

## 데이터 및 모델 관련 파일

- `data/`: 공개 가능한 샘플 데이터만 둡니다. 실제 학습/평가 데이터는 커밋하지 않습니다.
- `data/emotion_data.csv`: 원본 감정 학습 데이터입니다. 로컬에만 보관하고 GitHub에는 올리지 않습니다.
- `kc_saved_model/`: 감정 분석 worker가 사용하는 로컬 HuggingFace 모델 디렉터리입니다. 모델 본체는 저장소에 포함하지 않고 `.gitkeep`만 커밋합니다.
- `artifacts/model_tokenizer/`: tokenizer/config 산출물 폴더입니다. 실제 산출물은 저장소에 포함하지 않고 `.gitkeep`만 커밋합니다.

## 문서

- `docs/PROJECT_STRUCTURE.md`: 프로젝트 폴더 구조 설명입니다.
- `docs/PUBLIC_RELEASE_CHECKLIST.md`: GitHub 공개 전 민감 파일, 모델, 데이터, 문서 링크, 테스트 상태를 확인하는 체크리스트입니다.
- `docs/PUBLIC_RELEASE_AUDIT.md`: 현재 공개 점검 결과와 제거한 운영 설정을 기록한 문서입니다.
- docs/EMOTION_WORKER.md: 감정 분석 worker 입출력과 모델 파일 필요 범위를 정리한 문서입니다.
- docs/EMOTION_LABEL_POLICY.md: 감정 라벨 체계와 놀람 라벨 해석 근거를 정리한 문서입니다.
- docs/EMOTION_LABEL_GUIDELINES.md: 사람이 라벨을 검토할 때 사용할 primary/secondary 감정 판단 기준을 정리한 문서입니다.
- docs/EMOTION_MODEL_IMPROVEMENT.md: 감정 모델 업그레이드 판단 기준과 개선 계획을 정리한 문서입니다.
- docs/EMOTION_DATA_AUDIT.md: 원본 감정 학습 데이터의 개수, 라벨 분포, 중복, 품질 한계를 점검한 문서입니다.
- docs/EMOTION_DATA_CLEANING_AND_REEVAL.md: 원본 데이터 중복 제거, 누수 방지 split, cleaned test 재평가, 취약 라벨 보강 후보 추출 결과를 정리한 문서입니다.
- docs/EMOTION_BOUNDARY_REVIEW.md: 사람이 검토한 `상처/슬픔/불안` 라벨 경계와 primary/secondary 감정 판단 결과를 정리한 문서입니다.
- docs/RECOMMENDER_POLICY.md: 추천 점수식의 의도, 정당성, 한계, 다음 검증 방향을 정리한 문서입니다.
- docs/RECOMMENDER_EVALUATION.md: 추천 ranking metric과 오프라인 평가 방법을 정리한 문서입니다.

## 공개 저장소 주의사항

- `.env`, API key, DB 비밀번호, credential, service account 파일은 커밋하지 않습니다.
- 대용량 모델 본체는 GitHub에 올리지 않고 로컬 경로 또는 별도 배포 방식으로 관리합니다.
- 실제 학습/평가 데이터와 tokenizer 산출물도 공개 저장소에 포함하지 않습니다.
- 포트폴리오 공개 전 실제 사용자 데이터와 민감한 운영 로그가 포함되어 있지 않은지 확인합니다.


## 최근 구조 정리

- `ai/infra/mq_emotion.py`: 감정 분석 MQ worker 실행 파일
- `ai/infra/mq_insight.py`: 주간 인사이트 MQ worker 실행 파일
- `ai/infra/emotion_message.py`: 감정 요청 parsing과 결과 포맷
- `ai/infra/insight_message.py`: 인사이트 요청 parsing
- `ai/infra/insight_policy.py`: 인사이트 근거 수준 판단과 가벼운 조언 정책
