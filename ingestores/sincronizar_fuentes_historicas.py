#!/usr/bin/env python3
"""Sincroniza fuentes históricas de datos desde un catálogo SMB/GIO."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import unquote


DATA_EXTENSIONS = {".csv", ".xls", ".xlsx", ".zip", ".rar", ".mdb", ".sqlite", ".db", ".json"}
DATA_TERMS = ("smec", "operaci", "balance", "generaci", "hidric", "cnd", "alarma", "restric", "evento")


def local_relative(path: str) -> Path:
    marker = "/operaciones/"
    decoded = unquote(path)
    return Path(decoded.split(marker, 1)[1]) if marker in decoded else Path(Path(decoded).name)


def selected(row: dict[str, str]) -> bool:
    ext = row["extension"].lower()
    path = row["path"].lower()
    return ext in DATA_EXTENSIONS and any(term in path for term in DATA_TERMS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    args.raw_root.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    rows = [row for row in csv.DictReader(args.catalog.open(encoding="utf-8")) if selected(row)]
    counts = {"ok": 0, "skip": 0, "error": 0}

    def write_status(index: int, current: str, state: str) -> None:
        args.status.parent.mkdir(parents=True, exist_ok=True)
        args.status.write_text(json.dumps({
            "estado": state,
            "progreso": index,
            "total": len(rows),
            "porcentaje": round(index * 100 / len(rows), 2) if rows else 100.0,
            "actual": current,
            "ok": counts["ok"],
            "omitidos": counts["skip"],
            "errores": counts["error"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_status(0, "", "ejecutando")
    with args.log.open("a", encoding="utf-8") as log:
        for index, row in enumerate(rows, 1):
            source = row["path"]
            destination = args.raw_root / local_relative(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.stat().st_size == int(row["size_bytes"] or 0):
                counts["skip"] += 1
                log.write(f"SKIP\t{index}/{len(rows)}\t{source}\t{destination}\n")
                write_status(index, source, "ejecutando")
                continue
            status = "ERROR"
            for attempt in range(1, args.retries + 2):
                try:
                    result = subprocess.run(
                        ["gio", "copy", source, str(destination)],
                        capture_output=True, text=True, timeout=args.timeout,
                    )
                    if result.returncode == 0 and destination.exists():
                        status = f"OK sha256={sha256(destination)}"
                        counts["ok"] += 1
                        break
                    status = f"ERROR rc={result.returncode} {result.stderr.strip()}"
                except subprocess.TimeoutExpired:
                    status = f"TIMEOUT attempt={attempt}"
                time.sleep(2)
            if not status.startswith("OK"):
                counts["error"] += 1
            log.write(f"{status}\t{index}/{len(rows)}\t{source}\t{destination}\n")
            log.flush()
            write_status(index, source, "ejecutando")
            print(f"{status.split()[0]} {index}/{len(rows)} {destination}", flush=True)
    write_status(len(rows), "", "completado")


if __name__ == "__main__":
    main()
