"""Dashboard discovery.

A dashboard is a directory under DASHBOARDS_DIR containing dashboard.yaml. It owns
its own Postgres schema, its own migrations, its own ingest module and its own
context.md. Nothing here is shared between dashboards except these contracts.
"""
import hashlib
import importlib.util
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .config import settings


@dataclass
class Dataset:
    slug: str
    display_name: str
    table_name: str
    natural_key: list[str]
    required_columns: list[str] = field(default_factory=list)


@dataclass
class Dashboard:
    slug: str
    name: str
    version: int
    db_schema: str
    dir: Path
    manifest: dict[str, Any]
    datasets: dict[str, Dataset]
    context_sha: str | None

    _module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        if self._module is None:
            path = self.dir / "ingest.py"
            spec = importlib.util.spec_from_file_location(f"dashboards.{self.slug}.ingest", path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"{self.slug}: cannot import {path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._module = mod
        return self._module

    def dataset(self, slug: str) -> Dataset:
        if slug not in self.datasets:
            raise KeyError(f"{self.slug} has no dataset '{slug}'")
        return self.datasets[slug]


def _load(directory: Path) -> Dashboard:
    manifest = yaml.safe_load((directory / "dashboard.yaml").read_text()) or {}
    slug = manifest["slug"]
    context = directory / "context.md"
    datasets = {
        ds_slug: Dataset(
            slug=ds_slug,
            display_name=spec.get("display_name", ds_slug),
            table_name=spec["table"],
            natural_key=list(spec["natural_key"]),
            required_columns=list(spec.get("required_columns", [])),
        )
        for ds_slug, spec in (manifest.get("datasets") or {}).items()
    }
    return Dashboard(
        slug=slug,
        name=manifest.get("name", slug),
        version=int(manifest.get("version", 1)),
        db_schema=manifest.get("schema", f"dash_{slug}"),
        dir=directory,
        manifest=manifest,
        datasets=datasets,
        context_sha=hashlib.sha256(context.read_bytes()).hexdigest() if context.exists() else None,
    )


@lru_cache(maxsize=1)
def _cache() -> dict[str, Dashboard]:
    root = Path(settings.dashboards_dir)
    found = {}
    for manifest_path in sorted(root.glob("*/dashboard.yaml")):
        dash = _load(manifest_path.parent)
        found[dash.slug] = dash
    return found


def discover(refresh: bool = False) -> list[Dashboard]:
    if refresh:
        _cache.cache_clear()
    return list(_cache().values())


def get(slug: str) -> Dashboard:
    dash = _cache().get(slug)
    if dash is None:
        raise KeyError(f"unknown dashboard '{slug}'")
    return dash


def sync(conn) -> None:
    """Upsert the filesystem registry into core.dashboards / core.datasets."""
    import json

    with conn.cursor() as cur:
        for dash in discover(refresh=True):
            cur.execute(
                """
                insert into core.dashboards (slug, name, version, db_schema, context_sha, manifest, updated_at)
                values (%s, %s, %s, %s, %s, %s::jsonb, now())
                on conflict (slug) do update set
                  name = excluded.name, version = excluded.version, db_schema = excluded.db_schema,
                  context_sha = excluded.context_sha, manifest = excluded.manifest, updated_at = now()
                returning id
                """,
                (dash.slug, dash.name, dash.version, dash.db_schema,
                 dash.context_sha, json.dumps(dash.manifest)),
            )
            dash_id = cur.fetchone()["id"]
            for ds in dash.datasets.values():
                cur.execute(
                    """
                    insert into core.datasets
                      (dashboard_id, slug, display_name, table_name, natural_key, required_columns)
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (dashboard_id, slug) do update set
                      display_name = excluded.display_name, table_name = excluded.table_name,
                      natural_key = excluded.natural_key, required_columns = excluded.required_columns
                    """,
                    (dash_id, ds.slug, ds.display_name, ds.table_name,
                     ds.natural_key, ds.required_columns),
                )
    conn.commit()
