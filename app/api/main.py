"""대시보드 API 진입점: uv run uvicorn app.api.main:app --port 8000"""

from diecast_qa.dashboard.api import create_app

app = create_app()
