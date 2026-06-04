# portfolio

개인 프로젝트를 한 곳에 모아두는 저장소입니다.

각 프로젝트는 코드만 올리는 데서 끝내지 않고, 어떤 역할을 맡았는지와 어떤 부분을 검증했는지까지 함께 정리합니다.
지금은 GeoMemo-AI를 먼저 올려두었고, 이후 다른 프로젝트들도 `projects/` 아래에 추가할 예정입니다.

## 프로젝트

| 프로젝트 | 설명 |
| --- | --- |
| [GeoMemo-AI](projects/geomemo-ai) | 위치 기반 메모 서비스에서 감정 분석, 장소 추천, 주간 인사이트를 담당한 AI worker 모듈 |

## 구조

```text
portfolio/
  projects/
    geomemo-ai/
```

## 공개 기준

- 실제 `.env`, API key, DB password, credential은 올리지 않습니다.
- 원본 데이터와 대용량 모델 파일은 GitHub에 포함하지 않습니다.
- 공개 가능한 샘플 데이터, 테스트 코드, 기술 문서만 남깁니다.
