# GitHub 공개 전 체크리스트

이 문서는 GeoMemo-AI를 새 GitHub 저장소에 공개하기 전에 확인할 항목을 정리합니다.

## 1. 민감 파일 제외

다음 파일은 공개 저장소에 포함하지 않습니다.

- `.env`
- `.env.*`
- API key
- DB password
- credential 파일
- service account 파일
- `.pem`, `.key` 등 개인 키 파일

확인 명령:

```bash
git status --short
git check-ignore -v .env
```

`.env.sample`은 공개 가능하지만 실제 값은 넣지 않습니다.

## 2. 모델 파일 제외

감정 모델 본체와 tokenizer/config 산출물은 공개하지 않습니다.

공개 저장소에 남기는 파일:

- `kc_saved_model/.gitkeep`
- `artifacts/model_tokenizer/.gitkeep`

공개하지 않는 파일 예시:

- `model.safetensors`
- `pytorch_model.bin`
- `tokenizer.json`
- `tokenizer_config.json`
- `config.json`
- `vocab.txt`
- `special_tokens_map.json`

확인 명령:

```bash
git check-ignore -v kc_saved_model/model.safetensors
git check-ignore -v artifacts/model_tokenizer/tokenizer.json
```

## 3. 실제 데이터 제외

실제 학습/평가 데이터와 사람이 검토한 boundary review 파일은 공개하지 않습니다.

공개 가능한 파일:

- `data/sample_emotion_data.csv`
- `data/sample_emotion_domain_eval.csv`

공개하지 않는 파일 예시:

- `data/emotion_data.csv`
- `data/emotion_data_cleaned.csv`
- `data/emotion_train.csv`
- `data/emotion_val.csv`
- `data/emotion_test.csv`
- `data/emotion_boundary_candidates.csv`
- `data/emotion_boundary_review_template.xlsx`
- `data/emotion_label_corrections.csv`
- `data/emotion_secondary_labels.csv`

확인 명령:

```bash
git check-ignore -v data/emotion_data.csv
git check-ignore -v data/emotion_boundary_review_template.xlsx
```

## 4. 생성 리포트 제외

`reports/` 아래의 평가 결과는 로컬 검증 산출물로 관리하고 공개 저장소에는 포함하지 않습니다.

확인 명령:

```bash
git check-ignore -v reports/emotion_cleaned_test_summary.json
```

필요한 수치는 README와 docs 문서에 요약해서 남깁니다.

## 5. 문서 링크 확인

README에서 연결되는 주요 문서가 존재하는지 확인합니다.

- `docs/PROJECT_STRUCTURE.md`
- `docs/PORTFOLIO_CASE_STUDY.md`
- `docs/PORTFOLIO_ROADMAP.md`
- `docs/PUBLIC_RELEASE_CHECKLIST.md`
- `docs/MQ_MESSAGE_CONTRACTS.md`
- `docs/EMOTION_WORKER.md`
- `docs/EMOTION_LABEL_POLICY.md`
- `docs/EMOTION_LABEL_GUIDELINES.md`
- `docs/SYNTHETIC_TRAINING_DATA.md`
- `docs/EMOTION_DATA_AUDIT.md`
- `docs/EMOTION_DATA_CLEANING_AND_REEVAL.md`
- `docs/EMOTION_BOUNDARY_REVIEW.md`
- `docs/EMOTION_CONFIDENCE_POLICY.md`
- `docs/EMOTION_MODEL_IMPROVEMENT.md`
- `docs/INSIGHT_POLICY.md`
- `docs/RECOMMENDER_POLICY.md`
- `docs/RECOMMENDER_EVALUATION.md`
- `docs/RECOMMENDER_LOG_SCHEMA.md`

## 6. 테스트 확인

공개 전 최소 확인:

```bash
python -m unittest tests.test_recommender
git diff --check
```

현재 기대 상태:

- DB/MQ 없이 unit test 통과
- whitespace error 없음
- `.env`, 모델 본체, 실제 데이터, 생성 리포트가 Git 추적 대상에 없음

## 7. GitHub 공개 설명

새 GitHub 저장소 설명에는 다음처럼 적는 것이 안전합니다.

```text
Portfolio-ready AI worker module for GeoMemo: Korean memo emotion classification, emotion-aware place recommendation, weekly insight policy, and MQ message contracts. Refactored from a team project with documented model/data limitations and DB/MQ-free tests.
```

README에서는 다음 점을 명확히 유지합니다.

- 이 프로젝트는 production ML 성능을 주장하지 않습니다.
- 감정 모델은 GPT 합성 데이터 기반 baseline입니다.
- 실제 데이터와 모델 파일은 공개하지 않습니다.
- 핵심 가치는 구현 자체보다 검증, 정리, 문서화, 한계 인식, 개선 과정입니다.
