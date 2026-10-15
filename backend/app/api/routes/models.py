"""Models HTTP routes; business logic stays in services."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.body import bounded_json
from backend.app.api.dependencies import actor, get_services
from backend.app.domain.schemas import TrainingDataset

router = APIRouter()


@router.get("/api/v1/model")
def model_status(request: Request):
    services = get_services(request)
    return services.model.status()


@router.post("/api/v1/model/train")
async def train_model(request: Request):
    services = get_services(request)
    dataset = await bounded_json(request, TrainingDataset)
    if isinstance(dataset, JSONResponse):
        return dataset
    return await run_in_threadpool(services.engine.train, dataset, actor(request))


@router.post("/api/v1/model/train/demo")
def train_demo_model(request: Request):
    services = get_services(request)
    return services.engine.train(actor=actor(request))
