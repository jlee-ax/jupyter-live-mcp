# 0.1.0 검증 기록

- 코드·패키지 검증일: 2026-10-10
- 실행 환경: macOS, Python 3.12

## 검사 결과

| 항목 | 결과 |
| --- | --- |
| 전체 테스트 | 18 passed in 53.51s, 실패·건너뜀 없음 |
| Ruff 코드·포맷 검사 | 통과 |
| basedpyright | 오류·경고 0개 |
| wheel·소스 배포 파일 빌드 | 통과 |
| 별도 uv 도구 환경에 wheel 설치 | CLI 환경 검사에서 `ready=true` 확인 |
| 설치된 wheel의 MCP 초기 연결 | 관리 도구 7개, `selection_required` 상태, Jupyter 미기동 확인 |
| 새 분석 환경의 서버·세션 제어 테스트 | 6개 통과 |

## 세션과 노트북 실행

`teaching-env`와 `research-env`에서 각각 노트북을 생성하고 MCP로 코드 셀을 삽입·실행·조회했습니다. 출력에서 선택한 환경의 `sys.prefix`와 계산 결과 `42`를 확인했습니다.

커널의 실행 환경은 `sys.executable`과 `sys.prefix`를 선택한 환경과 대조해 검증합니다. 검증 실패 시 MCP 백엔드와 Jupyter 세션을 종료하고 오류를 반환합니다.

다음 동작을 확인했습니다.

- 가상환경 Python의 심볼릭 링크 유지와 필수 패키지 버전 검사
- 기존 환경 경로 덮어쓰기 거부
- 인증되지 않은 Jupyter 접근 거부
- 활성 세션의 Python 교체 거부
- 백엔드 시작 실패 시 세션 정리
- MCP 연결 종료 후 Jupyter 유지와 명시적 종료

## 의존성 호환

`code-sandboxes 1.10.0`은 Datalayer `jupyter-mcp-server 1.1.4`가 사용하는 `jupyter` 백엔드 이름을 인식하지 못했습니다. 환경 검사와 설치 조건을 `code-sandboxes==0.17.0`으로 고정한 뒤 실행을 확인했습니다.

## GitHub 소스 설치

[커밋 7d4f4c0](https://github.com/jlee-ax/jupyter-live-mcp/commit/7d4f4c06f98d0358177510799626a2f00b065773)의 소스를 별도 uv 도구 환경에 설치했습니다. 설치된 CLI로 분석 환경을 검사해 `ready=true`를 확인했습니다.

## Codex CLI 검증 — 2026-10-15

[커밋 99fb018](https://github.com/jlee-ax/jupyter-live-mcp/commit/99fb018628523ca9b21531c7498c96ad31915222)의 소스 설치와 수동 MCP 등록 후, Codex CLI에서 환경 후보를 조회하고 프로젝트의 `.venv`를 선택했습니다. 선택한 환경의 Jupyter 서버·커널 실행과 JupyterLab 접속을 확인했습니다.

[화면 기록](docs/assets/codex-install-and-start.gif)은 JupyterLab 터미널에서 촬영했으며, 브라우저 인증에는 검증용 로컬 도구를 사용했습니다.

## 통합 테스트 재현

macOS에서 저장소 루트를 기준으로 실행합니다. 개발 환경에 Jupyter 의존성을 설치하고, `JUPYTER_LIVE_TEST_PYTHON`을 지정해 세션 수명주기 검증을 포함합니다.

```sh
uv sync --group dev --python 3.12
uv pip install --python .venv/bin/python \
  'jupyterlab>=4,<5' \
  'jupyter-collaboration>=4,<5' \
  'ipykernel>=6,<8' \
  'jupyter-mcp-server==1.1.4' \
  'code-sandboxes==0.17.0'
JUPYTER_LIVE_TEST_PYTHON="$PWD/.venv/bin/python" \
  uv run --no-sync pytest -m integration
```

## 검증 범위

| 대상 | 상태 |
| --- | --- |
| macOS·Python 3.12의 CLI, MCP, Jupyter 실행 | 검증 완료 |
| 수동 MCP 등록 후 Codex CLI의 환경 선택·Jupyter 실행 | 2026-10-15 검증 완료 |
| Windows·Linux 실행 | 미검증 |
| Codex 플러그인 설치 후 환경 선택 질문이 표시되는 UI 과정 | 미검증 |
| GitHub Actions 실행 | 미검증. 설정은 `ci/github-actions.yml`에 템플릿으로 제공 |
