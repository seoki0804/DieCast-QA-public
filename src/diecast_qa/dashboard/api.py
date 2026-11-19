"""대시보드 API (FastAPI). scripts/11_dashboard_data.py가 만든 파일을 읽기만 한다.

실행: uv run uvicorn app.api.main:app --port 8000
"""

from __future__ import annotations

import gzip
import json
from functools import cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from diecast_qa.config import Paths


class DashboardStore:
    """results/dashboard/의 JSON(gzip)을 처음 요청할 때 읽어 메모리에 둔다."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.read = cache(self._read)

    def _read(self, name: str) -> dict:
        path = self.data_dir / f"{name}.json.gz"
        if not path.exists():
            raise KeyError(name)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def meta(self) -> dict:
        return self.read("meta")

    def summary(self) -> dict:
        return self.read("summary")

    def scenario(self, scenario_id: str) -> dict:
        if scenario_id not in {s["id"] for s in self.meta()["scenarios"]}:
            raise KeyError(scenario_id)
        return self.read(f"scenarios/{scenario_id}")


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = DashboardStore(data_dir or Paths().results_dir / "dashboard")
    app = FastAPI(title="DieCast-QA 대시보드 API", version="1.0")
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                       allow_headers=["*"])  # fmt: skip

    def scenario_or_404(scenario_id: str) -> dict:
        try:
            return store.scenario(scenario_id)
        except KeyError:
            raise HTTPException(404, f"알 수 없는 시나리오: {scenario_id}") from None

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta() -> dict:
        return store.meta()

    @app.get("/api/summary")
    def summary() -> dict:
        return store.summary()

    @app.get("/api/scenarios/{scenario_id}")
    def scenario(scenario_id: str) -> dict:
        data = scenario_or_404(scenario_id)
        return {"meta": data["meta"], "limits": data["limits"]}

    @app.get("/api/scenarios/{scenario_id}/shots")
    def shots(scenario_id: str, offset: int = Query(0, ge=0),
              limit: int = Query(200, ge=1, le=2000)) -> dict:  # fmt: skip
        rows = scenario_or_404(scenario_id)["shots"]
        return {"offset": offset, "total": len(rows), "shots": rows[offset : offset + limit]}

    @app.get("/api/scenarios/{scenario_id}/limits")
    def limits(scenario_id: str) -> dict:
        return scenario_or_404(scenario_id)["limits"]

    @app.get("/api/scenarios/{scenario_id}/alarms")
    def alarms(scenario_id: str) -> list[dict]:
        return scenario_or_404(scenario_id)["alarms"]

    return app
