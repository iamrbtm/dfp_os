from __future__ import annotations


def test_openapi_json_endpoint(client):
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    spec = resp.get_json()
    assert spec is not None
    assert spec.get("openapi", "").startswith("3.")
    assert "info" in spec
    assert "paths" in spec
    assert spec["info"].get("title") is not None


def test_openapi_info(client):
    resp = client.get("/api/openapi.json")
    spec = resp.get_json()
    info = spec.get("info", {})
    assert info.get("title") == "Dude Fish OS API"
    assert info.get("version") is not None


def test_openapi_has_crud_resources(client):
    resp = client.get("/api/openapi.json")
    spec = resp.get_json()
    paths = spec.get("paths", {})
    important_endpoints = [
        "/api/v1/products",
        "/api/v1/categories",
        "/api/v1/customers",
        "/api/v1/orders",
        "/api/v1/markets",
        "/api/v1/printers",
        "/api/v1/expenses",
        "/api/v1/pos-sessions",
        "/api/v1/analytics/summary",
        "/api/v1/settings",
        "/api/v1/themes",
    ]
    for ep in important_endpoints:
        assert any(ep in p for p in paths), f"Missing endpoint: {ep}"


def test_openapi_all_paths_have_responses(client):
    resp = client.get("/api/openapi.json")
    spec = resp.get_json()
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, op in methods.items():
            if method == "parameters":
                continue
            assert "responses" in op, f"{path} [{method}] missing responses"


def test_openapi_crud_has_request_bodies(client):
    resp = client.get("/api/openapi.json")
    spec = resp.get_json()
    paths = spec.get("paths", {})
    post_paths = [(p, m) for p, ms in paths.items() for m in ms if m == "post"]
    assert len(post_paths) > 0, "No POST endpoints found"
    for path, method in post_paths:
        op = paths[path][method]
        if "requestBody" not in op:
            if "api-tokens" in path or path.endswith("/exports/markets.csv"):
                continue
            assert False, f"{path} POST missing requestBody"


def test_openapi_all_schemas_have_properties(client):
    resp = client.get("/api/openapi.json")
    spec = resp.get_json()
    schemas = spec.get("components", {}).get("schemas", {})
    assert len(schemas) > 0, "No schemas found in OpenAPI spec"
    for name, schema in schemas.items():
        if schema.get("type") == "object":
            assert "properties" in schema or "allOf" in schema, f"Schema {name} has no properties"


def test_swagger_ui_loaded(client):
    resp = client.get("/api/docs")
    assert resp.status_code in (200, 302)


def test_redoc_ui_loaded(client):
    resp = client.get("/api/redoc")
    assert resp.status_code == 200
    assert b"Redoc" in resp.data or b"redoc" in resp.data
