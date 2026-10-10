# Changelog

## 0.1.0 — 2026-10-10

- Jupyter 시작 전 Python 환경 탐색과 사용자 지정 인터프리터 선택.
- 환경 검사, 가상환경 생성, 선택한 환경에 의존성 설치.
- 선택한 Python으로 JupyterLab과 MCP 백엔드 기동, 커널의 실행 환경 검증.
- Datalayer `jupyter-mcp-server==1.1.4`를 통한 노트북 조작과 호환되는 `code-sandboxes==0.17.0` 사용.
- MCP 연결 종료 후 Jupyter 세션 유지와 세션별 명시적 종료.
- Codex 플러그인 설정, Jupyter 작업 스킬, GitHub Actions 템플릿.
