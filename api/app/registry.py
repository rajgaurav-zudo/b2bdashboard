"""Sources and dashboard discovery.

A dashboard is a directory under DASHBOARDS_DIR containing dashboard.yaml. It owns
its own Postgres schema, its own migrations, its own ingest module and its own
context.md. Nothing here is shared between dashboards except these contracts.

A *source* is one step above that: a kind of CRM export, declared once in
sources.yaml and uploaded once. Dashboards say which source feeds each of their
datasets, so one applications export can be read by any number of dashboards
into any number of different tables. The source owns what the file is; the
dashboard owns what it takes out of it.
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
class Source:
    """A kind of file the platform accepts, independent of any dashboard."""
    slug: str
    display_name: str
    description: str = ""
    # normalised header fragments that must all be present. Checked before the
    # file is stored, so the wrong export is refused rather than loaded.
    identified_by: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    slug: str
    display_name: str
    table_name: str
    natural_key: list[str]
    # which uploaded file feeds this table. Defaults to the dataset's own slug,
    # which is what every dataset written before sources existed relied on.
    source: str = ""
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

    _modules: dict[str, ModuleType] = field(default_factory=dict)

    def load_module(self, name: str) -> ModuleType:
        """Import a python file from this dashboard's directory by path.

        Dashboards are plain directories, not packages, so they are loaded by
        location. Two dashboards may both define `metrics.py` without colliding.
        """
        if name not in self._modules:
            path = self.dir / f"{name}.py"
            if not path.exists():
                raise FileNotFoundError(f"{self.slug} has no {name}.py")
            spec = importlib.util.spec_from_file_location(f"dashboards.{self.slug}.{name}", path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"{self.slug}: cannot import {path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._modules[name] = mod
        return self._modules[name]

    @property
    def module(self) -> ModuleType:
        return self.load_module("ingest")

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
            source=spec.get("source") or ds_slug,
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
def _sources() -> dict[str, Source]:
    path = Path(settings.sources_file)
    if not path.exists():
        return {}
    declared = yaml.safe_load(path.read_text()) or {}
    return {
        slug: Source(
            slug=slug,
            display_name=(spec or {}).get("display_name", slug),
            description=((spec or {}).get("description") or "").strip(),
            identified_by=list((spec or {}).get("identified_by") or []),
        )
        for slug, spec in declared.items()
    }


def sources(refresh: bool = False) -> list[Source]:
    if refresh:
        _sources.cache_clear()
    return list(_sources().values())


def source(slug: str) -> Source:
    found = _sources().get(slug)
    if found is None:
        raise KeyError(f"unknown source '{slug}'")
    return found


def consumers(source_slug: str) -> list[tuple[Dashboard, Dataset]]:
    """Every (dashboard, dataset) fed by this source, in a stable order.

    This is the whole fan-out. A dashboard appears here because its own manifest
    named the source -- nothing registers a dashboard against a source on its
    behalf, so adding one cannot change what another already receives.
    """
    return [
        (dash, ds)
        for dash in discover()
        for ds in dash.datasets.values()
        if ds.source == source_slug
    ]


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
    """Upsert the filesystem registry into core.sources / dashboards / datasets."""
    import json

    with conn.cursor() as cur:
        source_ids: dict[str, int] = {}
        for src in sources(refresh=True):
            cur.execute(
                """
                insert into core.sources (slug, display_name, description, identified_by, updated_at)
                values (%s, %s, %s, %s, now())
                on conflict (slug) do update set
                  display_name = excluded.display_name, description = excluded.description,
                  identified_by = excluded.identified_by, updated_at = now()
                returning id
                """,
                (src.slug, src.display_name, src.description, src.identified_by),
            )
            source_ids[src.slug] = cur.fetchone()["id"]

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
                if ds.source not in source_ids:
                    raise KeyError(
                        f"{dash.slug}.{ds.slug} declares source '{ds.source}', "
                        f"which is not in sources.yaml ({', '.join(sorted(source_ids)) or 'empty'})"
                    )
                cur.execute(
                    """
                    insert into core.datasets
                      (dashboard_id, slug, display_name, table_name, natural_key,
                       required_columns, source_id)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (dashboard_id, slug) do update set
                      display_name = excluded.display_name, table_name = excluded.table_name,
                      natural_key = excluded.natural_key,
                      required_columns = excluded.required_columns,
                      source_id = excluded.source_id
                    """,
                    (dash_id, ds.slug, ds.display_name, ds.table_name,
                     ds.natural_key, ds.required_columns, source_ids[ds.source]),
                )
    conn.commit()
