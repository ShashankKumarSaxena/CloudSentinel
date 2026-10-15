"""Operations HTTP routes; business logic stays in services."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.api.dependencies import actor, get_services
from backend.app.domain.schemas import ScheduleCreate, ScheduleUpdate

router = APIRouter()


@router.get("/api/v1/alerts")
def alerts(
    request: Request,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000000),
):
    services = get_services(request)
    return services.operations.list_alerts(limit, offset)


@router.post("/api/v1/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str, request: Request):
    services = get_services(request)
    services.operations.acknowledge(alert_id, actor(request))
    return {"acknowledged": True}


@router.post("/api/v1/alerts/{alert_id}/retry")
def retry_alert(alert_id: str, request: Request):
    services = get_services(request)
    services.operations.retry_delivery(alert_id, actor(request))
    return {"queued": True}


@router.get("/api/v1/schedules")
def schedules(request: Request):
    services = get_services(request)
    return services.operations.list_schedules()


@router.post("/api/v1/schedules", status_code=201)
def create_schedule(request: Request, body: ScheduleCreate):
    services = get_services(request)
    if services.settings.production:
        if body.kind == "demo":
            raise HTTPException(403, "Synthetic schedules are available only in demo mode.")
        services.connections.resolve(body.collection)
    return services.operations.create_schedule(body, actor(request))


@router.patch("/api/v1/schedules/{schedule_id}")
def update_schedule(schedule_id: str, request: Request, body: ScheduleUpdate):
    services = get_services(request)
    return services.operations.update_schedule(schedule_id, body, actor(request))


@router.post("/api/v1/schedules/{schedule_id}/run", status_code=201)
def run_schedule(schedule_id: str, request: Request):
    services = get_services(request)
    if services.settings.production:
        return services.operations.run_soon(schedule_id, actor(request))
    claim = services.operations.claim_schedule(schedule_id)
    return services.worker.execute(claim, actor(request))


@router.get("/api/v1/monitor/runs")
def monitor_runs(request: Request):
    services = get_services(request)
    return services.operations.list_runs()


@router.get("/api/v1/operations")
def operation_status(request: Request):
    services = get_services(request)
    heartbeat = services.jobs.worker_status()
    state = services.worker.status()
    if services.settings.production:
        state.update(
            enabled=True,
            running=bool(
                heartbeat
                and heartbeat["status"] == "running"
                and (
                    datetime.fromisoformat(heartbeat["updated_at"])
                    > datetime.now(timezone.utc)
                    - timedelta(seconds=services.settings.worker_stale_seconds)
                )
            ),
            last_tick=heartbeat["updated_at"] if heartbeat else None,
        )
    return state | {
        "schedules": len(services.operations.list_schedules()),
        "unread_alerts": services.operations.list_alerts()["unread"],
        "mode": services.settings.mode,
    }


@router.get("/api/v1/audit")
def audit_log(request: Request):
    services = get_services(request)
    return services.operations.audit_records()
