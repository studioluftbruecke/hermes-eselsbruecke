"""Backend routes for the Eselsbrücke Desktop page, mounted at `/api/plugins/eselsbruecke/`.

    GET  /health                    {ok, schema, version, time_zone}
    GET  /toolbox                   the toolbox file (tools, dashboard, world clock places, status bar),
                                    every tool with its switch, hash
    POST /toolbox                   {op: switch, module, on} |
                                    {op: save, toolbox, base_hash} (409 when the file changed) |
                                    {op: restore, version}
    GET  /toolbox/versions          saved versions, newest first
    GET  /pad[?date=]               a day (today rolls over on first read), = results, queued prompts
    GET  /pad/markdown[?date=]      the day as Markdown (Copy as Markdown)
    POST /pad/lines                 {op: add|update|delete|restore|card, ...}; card makes a triage kanban card
    GET  /timer, POST /timer        the running timer; {op: start|pause|resume|stop, op_id?, at?, ...}
                                    (an op_id applied before answers duplicate: true)
    POST /presence                  the Desktop chip's heartbeat (the alert tick stays silent while fresh)
    GET  /alerts, POST /alerts/reconcile   the tick job's state; make it match the switch
    GET  /tips                      built-in and own productivity tips
    GET  /timelog[?date=]           a week: entries, totals per client and project, running timer, clients
    POST /timelog                   a click: {op: start|stop|add|edit|delete|undo|client, ...}
    POST /timelog/ops               the Desktop outbox: {ops: [...]}, each op_id stored once
    GET  /timelog/export[?date=]    the week as CSV text
    GET  /data/o200k                the o200k ranks (2.3 MB JSON) for the page's exact token count
    POST /run/{engine}              calc | format | convert | text | generate: {action, ...} as the agent
                                    tool takes it; 200 with ok true/false, 409 when the tool is off

Every answer carries `schema`; errors are {ok: false, error, message} with a 4xx status. These are the
user's own clicks (author `user`), so no unattended check runs here: for every profile
but the dashboard's own, routes run in the profile's plugin host child, which has
HERMES_PLUGIN_HOST_PROCESS=1.

Hermes loads this file as a standalone module, so the plugin folder is loaded as a package by path.
The data folder is computed per call from the bound Hermes home.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import FileResponse, JSONResponse

PLUGIN = "eselsbruecke"
_PACKAGE = "hermes_eselsbruecke_dashboard"

router = APIRouter()


def _plugin():
    module = sys.modules.get(_PACKAGE)
    if module is not None:
        return module
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(_PACKAGE, root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the {PLUGIN} package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)
    return module


def _mod(name: str):
    _plugin()
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _api():
    return _mod("api")


def _reply(result: "tuple[int, dict]") -> JSONResponse:
    status, body = result
    return JSONResponse(body, status_code=status)


# Sync handlers: FastAPI runs them on a worker thread.

@router.get("/health")
def health() -> JSONResponse:
    return _reply(_api().health())


@router.get("/toolbox")
def toolbox_get() -> JSONResponse:
    return _reply(_api().toolbox_get())


@router.post("/toolbox")
def toolbox_post(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().toolbox_post(body))


@router.get("/toolbox/versions")
def toolbox_versions() -> JSONResponse:
    return _reply(_api().toolbox_versions())


@router.post("/run/{engine}")
def run_engine(engine: str, body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().run_engine(engine, body))


@router.get("/pad")
def pad_get(date: Optional[str] = Query(None)) -> JSONResponse:
    return _reply(_api().pad_get(date))


@router.get("/pad/markdown")
def pad_markdown(date: Optional[str] = Query(None)) -> JSONResponse:
    return _reply(_api().pad_markdown(date))


@router.post("/pad/lines")
def pad_lines(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().pad_lines(body))


@router.get("/timer")
def timer_get() -> JSONResponse:
    return _reply(_api().timer_get())


@router.post("/timer")
def timer_post(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().timer_post(body))


@router.post("/presence")
def presence() -> JSONResponse:
    return _reply(_api().presence())


@router.get("/alerts")
def alerts_get() -> JSONResponse:
    return _reply(_api().alerts_get())


@router.post("/alerts/reconcile")
def alerts_reconcile() -> JSONResponse:
    return _reply(_api().alerts_reconcile())


@router.get("/tips")
def tips_get() -> JSONResponse:
    return _reply(_api().tips_get())


@router.get("/timelog")
def timelog_get(date: Optional[str] = Query(None)) -> JSONResponse:
    return _reply(_api().timelog_get(date))


@router.post("/timelog")
def timelog_post(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().timelog_post(body))


@router.post("/timelog/ops")
def timelog_ops(body: Any = Body(None)) -> JSONResponse:
    return _reply(_api().timelog_ops(body))


@router.get("/timelog/export")
def timelog_export(date: Optional[str] = Query(None)) -> JSONResponse:
    return _reply(_api().timelog_export(date))


@router.get("/data/o200k")
def data_o200k():
    status, body = _api().ranks_path()
    if status != 200:
        return JSONResponse(body, status_code=status)
    return FileResponse(body, media_type="application/json", headers={"Cache-Control": "private, max-age=86400"})
