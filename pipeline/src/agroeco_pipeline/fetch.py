"""Download sources and write committed, citable extracts.

Runs in GitHub Actions (network access). Raw copyrighted files are never
written to the repository: only extracted facts with cell references, public
domain SSURGO responses, and CC BY derived daily weather, plus a lock file of
URLs and SHA-256 checksums of every raw download.
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agroeco_pipeline import budget, sda, soils, weather
from agroeco_pipeline.common import (
    PipelineError,
    read_json,
    sha256_bytes,
    sources_dir,
    write_csv,
    write_json,
)
from agroeco_pipeline.xlsx import read_workbook

USER_AGENT = "AgroEcosystemSim-pipeline/0.1 (+https://github.com/Imrobbailey2/AgroEcosystemSim)"
FIGSHARE_API = "https://api.figshare.com/v2/articles/{id}"
STEPS = ("soils", "budgets", "weather")


def http(url: str, data: bytes | None = None, headers: dict[str, str] | None = None,
         attempts: int = 4, timeout: float = 120) -> bytes:
    """GET or POST with retries and exponential backoff. TLS verification stays on."""
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise PipelineError(f"download failed after {attempts} attempts: {url}: {last}")


def _post(url: str, body: bytes, headers: dict[str, str]) -> bytes:
    return http(url, data=body, headers=headers)


class Lock:
    """Records every raw download (URL, bytes, SHA-256)."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.step = ""

    def add(self, source: str, url: str, raw: bytes, note: str = "") -> None:
        self.entries.append(
            {"step": self.step, "source": source, "url": url, "bytes": len(raw),
             "sha256": sha256_bytes(raw), "note": note}
        )


def fetch_soils(region: dict[str, Any], out: Path, lock: Lock,
                post: Callable[[str, bytes, dict[str, str]], bytes] = _post) -> None:
    cfg = region["soils"]
    names = [f["muname"] for f in cfg["fields"]]
    raw, mapunits = sda.run_query(post, sda.mapunit_query(cfg["areasymbol"], names))
    lock.add(cfg["source"], sda.SDA_URL, raw, "mapunits")
    found = {m["muname"] for m in mapunits}
    missing = [n for n in names if n not in found]
    if missing:
        raise PipelineError(f"map units not found in {cfg['areasymbol']}: {missing}")
    raw_c, comps = sda.run_query(post, sda.component_query([str(m["mukey"]) for m in mapunits]))
    lock.add(cfg["source"], sda.SDA_URL, raw_c, "components")
    raw_h, hz = sda.run_query(post, sda.horizon_query([str(c["cokey"]) for c in comps]))
    lock.add(cfg["source"], sda.SDA_URL, raw_h, "horizons")
    # Validate before writing so a bad fetch never lands.
    soils.build_soil_units(cfg["fields"], mapunits, comps, hz, cfg["max_depth_cm"],
                           cfg["source"], cfg["areasymbol"])
    write_json(out / "sda_mapunits.json", mapunits)
    write_json(out / "sda_components.json", comps)
    write_json(out / "sda_horizons.json", hz)


def fetch_budgets(region: dict[str, Any], registry: dict[str, dict[str, Any]], out: Path,
                  lock: Lock, get: Callable[[str], bytes] = http) -> None:
    labels = region["budget_labels"]
    for b in region["budgets"]:
        url = registry[b["source"]]["url"]
        raw = get(url)
        lock.add(b["source"], url, raw)
        try:
            cells = read_workbook(raw)
        except ValueError as exc:
            raise PipelineError(f"{url}: {exc}") from exc
        required = [lbl for lbl in labels["required"] if b["tenure"] == "rented" or lbl != "Land rental cost"]
        optional = [lbl for lbl in labels["optional"] if lbl not in required]
        if b["tenure"] == "owned" and "Land rental cost" not in optional:
            optional.append("Land rental cost")
        rows = budget.extract_lines(cells, required, optional)
        write_csv(out / b["file"], rows, budget.FIELDS)


def _files_from(name: str, raw: bytes) -> list[tuple[str, bytes]]:
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            return [(n, zf.read(n)) for n in sorted(zf.namelist()) if not n.endswith("/")]
    return [(name, raw)]


def fetch_weather(region: dict[str, Any], out: Path, lock: Lock,
                  get: Callable[[str], bytes] = http) -> None:
    cfg = region["weather"]
    api = FIGSHARE_API.format(id=cfg["figshare_article_id"])
    meta_raw = get(api)
    lock.add(cfg["source"], api, meta_raw, "figshare article metadata")
    try:
        article = json.loads(meta_raw)
    except json.JSONDecodeError as exc:
        raise PipelineError("figshare API returned non-JSON") from exc
    files: list[tuple[str, bytes]] = []
    for f in sorted(article.get("files", []), key=lambda f: f["name"]):
        raw = get(f["download_url"])
        lock.add(cfg["source"], f["download_url"], raw, f["name"])
        files.extend(_files_from(f["name"], raw))
    if not files:
        raise PipelineError("figshare article lists no files")

    station = cfg.get("station_location")
    if station is None:
        metas = [(n, d) for n, d in files if "meta" in n.lower() and n.lower().endswith(".csv")]
        if not metas:
            raise PipelineError(
                f"no station metadata CSV in {[n for n, _ in files]}; add weather.station_location "
                "with a cited source to the region config"
            )
        station = weather.find_station(metas[0][1].decode("utf-8-sig"), cfg["station_id"], cfg["station_name"])
    data_files = [d for n, d in files if n.lower().endswith(".csv") and "meta" not in n.lower()]
    rows: list[dict[str, Any]] = []
    for data in data_files:
        rows.extend(
            weather.aggregate_daily(
                data.decode("utf-8-sig"), station["latitude"], station["elevation_m"], cfg["wind_height_m"]
            )
        )
    rows.sort(key=lambda r: r["date"])
    weather.select_years(rows, cfg["season_start"], cfg["season_end"])  # fail early
    write_json(out / "station.json", {**station, "station_id": cfg["station_id"],
                                      "name": cfg["station_name"], "source": cfg["source"]})
    write_csv(out / "weather_daily.csv", rows, weather.DAILY_FIELDS)


def run_fetch(region_id: str, only: list[str] | None = None) -> Path:
    base = sources_dir()
    region = read_json(base / "regions" / f"{region_id}.json")
    registry = {s["id"]: s for s in read_json(base / "sources.json")["sources"]}
    out = base / "extracted" / region_id
    out.mkdir(parents=True, exist_ok=True)
    lock = Lock()
    steps = only or list(STEPS)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise PipelineError(f"unknown fetch steps {unknown}; choose from {list(STEPS)}")
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock_path = out / "fetch-lock.json"
    previous = read_json(lock_path) if lock_path.exists() else {"downloads": [], "fetched_at": {}}
    fetched_at = dict(previous.get("fetched_at") or {})
    for step in steps:
        lock.step = step
        if step == "soils":
            fetch_soils(region, out, lock)
        elif step == "budgets":
            fetch_budgets(region, registry, out, lock)
        else:
            fetch_weather(region, out, lock)
        fetched_at[step] = now
    kept = [e for e in previous.get("downloads", []) if e.get("step") not in steps]
    write_json(
        lock_path,
        {"region": region_id, "fetched_at": fetched_at, "downloads": kept + lock.entries},
    )
    return out
