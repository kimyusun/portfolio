# GitHub 공개 점검 기록

점검일: 2026-06-04

이 문서는 GeoMemo-AI를 개인 GitHub 저장소에 공개하기 전에 확인한 결과를 기록합니다. 목표는 포트폴리오 공개 시 민감 정보, 실제 데이터, 대용량 모델 파일, 오래된 팀 운영 설정이 포함되지 않도록 하는 것입니다.

## 점검 요약

| 항목 | 결과 | 메모 |
| --- | --- | --- |
| `.env` | 제외 확인 | `.gitignore`의 `.env` 규칙으로 제외 |
| 실제 감정 데이터 CSV | 제외 확인 | `data/*.csv` 규칙으로 제외, sample CSV만 예외 |
| boundary review xlsx | 제외 확인 | `data/*.xlsx` 규칙으로 제외 |
| 모델 본체 | 제외 확인 | `kc_saved_model/*` 규칙으로 제외, `.gitkeep`만 허용 |
| tokenizer/config 산출물 | 제외 확인 | `artifacts/model_tokenizer/*` 규칙으로 제외, `.gitkeep`만 허용 |
| 평가 리포트 | 제외 확인 | `reports/` 규칙으로 제외 |
| README 문서 링크 | 통과 | README의 docs 링크 확인 완료 |
| 단위 테스트 | 통과 | `30`개 테스트 통과 |
| Python 문법 컴파일 | 통과 | `ai`, `scripts`, `dev`, `tests`, `run_all_workers.py` 컴파일 통과 |
| 커밋 후보 secret scan | 통과 | 실제 키/토큰 없음, `.env.sample` placeholder와 환경변수 이름만 탐지 |
| 오래된 GitHub Actions workflow | 제거 | 팀 저장소 Discord 알림 workflow는 GeoMemo-AI 전용 repo에 맞지 않아 제거 |

## 제외 확인한 주요 파일

다음 파일들은 공개 저장소에 포함하지 않습니다.

- `.env`
- `data/emotion_data.csv`
- `data/emotion_data_cleaned.csv`
- `data/emotion_train.csv`
- `data/emotion_val.csv`
- `data/emotion_test.csv`
- `data/emotion_boundary_candidates.csv`
- `data/emotion_boundary_review_template.xlsx`
- `data/emotion_label_corrections.csv`
- `data/emotion_secondary_labels.csv`
- `kc_saved_model/model.safetensors`
- `artifacts/model_tokenizer/tokenizer.json`
- `reports/emotion_cleaned_test_summary.json`

## 공개 가능한 파일

다음 파일들은 공개 저장소에 남겨도 됩니다.

- `.env.sample`
- `data/sample_emotion_data.csv`
- `data/sample_emotion_domain_eval.csv`
- `kc_saved_model/.gitkeep`
- `artifacts/model_tokenizer/.gitkeep`
- `docs/` 아래 정책/평가/공개 점검 문서
- `dev/sample_payloads/` 아래 샘플 payload
- `tests/test_recommender.py`

## 제거한 운영 설정

기존 저장소에는 `.github/workflows/discord-notify.yml`이 있었습니다. 이 workflow는 기존 팀 GitHub organization과 Discord webhook secret 이름에 의존하고 있었기 때문에, GeoMemo-AI 전용 repo에서는 동작하지 않거나 불필요한 운영 설정이 될 수 있습니다.

따라서 공개용 정리 과정에서 제거했습니다. 나중에 이 저장소에서 CI가 필요하면 테스트 실행 전용 workflow를 별도로 추가하는 것이 더 적절합니다.

## 확인한 명령

```bash
git check-ignore -v .env data/emotion_data.csv data/emotion_boundary_review_template.xlsx kc_saved_model/model.safetensors artifacts/model_tokenizer/tokenizer.json reports/emotion_cleaned_test_summary.json
python -m compileall -q ai scripts dev tests run_all_workers.py
python -m unittest discover -s tests -p "test*.py"
git diff --check
```

## 현재 판단

GitHub 공개 전 큰 보안 위험 요소는 대부분 정리되었습니다. 현재 공개 저장소는 개인 계정의 `GeoMemo-AI` 전용 repo로 관리합니다.

- `git status --short`에서 공개하면 안 되는 파일이 staged 상태가 아닌지 확인
- `.env`, 실제 데이터, 모델 파일이 Git 추적 대상에 없는지 확인
- GitHub README에서 링크와 Mermaid 다이어그램이 정상적으로 보이는지 확인
- 필요하면 테스트 전용 GitHub Actions workflow를 새로 작성
