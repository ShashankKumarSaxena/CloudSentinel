"""Describe cookie/CSRF security and streamed JSON inputs accurately for clients."""

from backend.app.api.permissions import PUBLIC_ROUTES, ROLE_RANK, minimum_role
from backend.app.domain.schemas import Inventory, LoginRequest, TrainingDataset
from backend.app.services.auth import COOKIE_NAME

BOUNDED_INPUTS = {
    "/api/v1/auth/login": LoginRequest,
    "/api/v1/scans/import": Inventory,
    "/api/v1/model/train": TrainingDataset,
}


def install_openapi(app):
    default_schema = app.openapi

    def schema():
        if app.openapi_schema is not None:
            return app.openapi_schema
        document = default_schema()
        components = document.setdefault("components", {})
        components.setdefault("securitySchemes", {}).update(
            {
                "WorkspaceSession": {"type": "apiKey", "in": "cookie", "name": COOKIE_NAME},
                "CsrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            }
        )
        definitions = components.setdefault("schemas", {})
        for path, model in BOUNDED_INPUTS.items():
            model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            definitions.update(model_schema.pop("$defs", {}))
            definitions[model.__name__] = model_schema
            document["paths"][path]["post"]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/" + model.__name__}
                    }
                },
            }
        for path, methods in document["paths"].items():
            for method, operation in methods.items():
                if (method.upper(), path) in PUBLIC_ROUTES:
                    operation["security"] = []
                    continue
                security = {"WorkspaceSession": []}
                if method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
                    security["CsrfToken"] = []
                operation["security"] = [security]
                required = minimum_role(method.upper(), path)
                operation["x-required-roles"] = [
                    role for role, rank in ROLE_RANK.items() if rank >= ROLE_RANK[required]
                ]
        return document

    app.openapi = schema
