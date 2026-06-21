from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

DEFAULT_OPENAPI_URL = "http://localhost:5000/api/openapi.json"
FALLBACK_PATH = Path("./openapi/openapi.json")


def _get_url() -> str:
    import os
    return os.getenv("DFPOS_OPENAPI_URL", DEFAULT_OPENAPI_URL)


def fetch_spec():
    url = _get_url()
    console.print(f"[bold]Fetching OpenAPI spec from:[/] {url}")

    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        spec = resp.json()
    except Exception as e:
        console.print(f"[red]Failed to fetch spec:[/] {e}", stderr=True)
        sys.exit(1)

    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FALLBACK_PATH, "w") as f:
        json.dump(spec, f, indent=2)

    info = spec.get("info", {})
    endpoint_count = len(spec.get("paths", {}))

    console.print(f"[green]Spec saved to:[/] {FALLBACK_PATH.resolve()}")
    console.print(f"  Title:    {info.get('title', '(untitled)')}")
    console.print(f"  Version:  {info.get('version', '(none)')}")
    console.print(f"  Paths:    {endpoint_count}")
    return 0


def validate_spec():
    spec_path = FALLBACK_PATH
    if not spec_path.exists():
        console.print(f"[red]Spec file not found:[/] {spec_path}", stderr=True)
        sys.exit(1)

    with open(spec_path) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON:[/] {e}", stderr=True)
            sys.exit(1)

    errors = _validate_openapi(spec)

    if errors:
        table = Table(title="Validation Errors", title_style="bold red")
        table.add_column("Severity", style="red")
        table.add_column("Message")
        for severity, msg in errors:
            table.add_row(severity, msg)
        console.print(table)
        console.print(f"\n[red]Found {len(errors)} issue(s)[/]")
        sys.exit(1)
    else:
        info = spec.get("info", {})
        paths = spec.get("paths", {})
        console.print(Panel.fit(
            f"[green]✓[/] OpenAPI spec is valid\n"
            f"  Title:   {info.get('title', '(untitled)')}\n"
            f"  Version: {info.get('version', '(none)')}\n"
            f"  Paths:   {len(paths)}\n"
            f"  File:    {spec_path.resolve()}",
            title="Spec Validation Passed",
        ))
    return 0


def _validate_openapi(spec: dict) -> list[tuple[str, str]]:
    errors = []

    if "openapi" not in spec:
        errors.append(("error", "Missing 'openapi' version field"))
    if "info" not in spec:
        errors.append(("error", "Missing 'info' block"))
    else:
        info = spec["info"]
        if "title" not in info:
            errors.append(("warning", "Missing 'info.title'"))
        if "version" not in info:
            errors.append(("warning", "Missing 'info.version'"))

    if "paths" not in spec:
        errors.append(("error", "Missing 'paths' block"))
    elif not spec["paths"]:
        errors.append(("warning", "No paths defined"))

    if spec.get("paths"):
        for path, methods in spec["paths"].items():
            for method, op in methods.items():
                if "responses" not in op:
                    errors.append(("warning", f"Path {path} [{method}] has no responses"))

    return errors


def build_docs():
    console.print("[bold]Building API docs...[/]")

    code = fetch_spec()
    if code != 0:
        console.print("[red]Fetch step failed. Aborting build.[/]", stderr=True)
        sys.exit(1)

    code = validate_spec()
    if code != 0:
        console.print("[red]Validate step failed. Aborting build.[/]", stderr=True)
        sys.exit(1)

    console.print("[green]✓ Build complete. Spec is ready for serving.[/]")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "fetch":
        sys.exit(fetch_spec())
    elif cmd == "validate":
        sys.exit(validate_spec())
    elif cmd == "build":
        sys.exit(build_docs())
    else:
        console.print(f"[red]Unknown command:[/] {cmd}")
        console.print("Usage: python app/cli.py [fetch|validate|build]")
        sys.exit(1)
