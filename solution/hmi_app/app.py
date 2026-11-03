"""Plant-style live display for the Zerobus pump demo (Databricks App backend).

Serves the React HMI from dist/ and three JSON endpoints:
  GET  /api/state       live tag values (silver), 10-minute trends (bronze), alarms, demo status
  POST /api/demo/start  run the zerobus_pump_demo job with a chosen fault and duration
  POST /api/demo/stop   cancel the demo run, then stop the live silver pipeline

Configuration comes from environment variables set by the bundle (resources/zerobus_pump.app.yml).
Set HMI_MOCK=1 to run locally against an in-process simulator instead of a workspace.
"""

import os
import pathlib
from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from plant_data import LiveSource, MockSource

source = MockSource() if os.environ.get("HMI_MOCK") else LiveSource()
app = FastAPI(title="Zerobus pump HMI")


class StartRequest(BaseModel):
    fault: Literal["none", "bearing", "cavitation"] = "bearing"
    minutes: int = Field(15, ge=1, le=60)


@app.get("/api/state")
def state():
    return source.state()


@app.post("/api/demo/start")
def start_demo(request: StartRequest):
    return source.start_demo(request.fault, request.minutes)


@app.post("/api/demo/stop")
def stop_demo():
    return source.stop_demo()


DIST = pathlib.Path(__file__).parent / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def index(path: str):
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))
