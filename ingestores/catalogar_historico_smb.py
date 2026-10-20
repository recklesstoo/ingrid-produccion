#!/usr/bin/env python3
"""Cataloga un recurso SMB ya montado mediante GIO, sin leer el contenido."""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import time
from collections import deque
from pathlib import PurePosixPath
from urllib.parse import quote, unquote


KEYWORDS = re.compile(
    r"smec|operaci[oó]n|balance|h[ií]dric|generaci[oó]n|cnd|alarma|restricci[oó]n|limitaci[oó]n|evento",
    re.IGNORECASE,
)
YEARS = re.compile(r"\b(20(?:1[4-9]|2[0-6]))\b")


def child_url(parent: str, name: str) -> str:
    return parent.rstrip("/") + "/" + quote(name, safe=" /&()_-.,#") + "/"


def list_location(location: str, timeout: int) -> list[tuple[str, int, str]]:
    result = subprocess.run(
        ["gio", "list", "-l", location], capture_output=True, text=True, timeout=timeout
    )
    rows = []
    for line in result.stdout.splitlines():
        fields = line.rsplit("\t", 2)
        if len(fields) != 3:
            continue
        name, size, kind = fields
        rows.append((name, int(size) if size.isdigit() else 0, kind))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Cataloga archivos históricos de un SMB montado en GIO.")
    parser.add_argument("--location", required=True, help="URL SMB, por ejemplo smb://host/share/")
    parser.add_argument("--output", required=True, help="CSV de catálogo local")
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--gio-timeout", type=int, default=15)
    args = parser.parse_args()

    started = time.time()
    queue: deque[str] = deque([args.location.rstrip("/") + "/"])
    seen: set[str] = set()
    records: list[dict[str, object]] = []
    while queue and time.time() - started < args.max_seconds:
        location = queue.popleft()
        if location in seen:
            continue
        seen.add(location)
        try:
            entries = list_location(location, args.gio_timeout)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for name, size, kind in entries:
            path = unquote(location + quote(name, safe=" /&()_-.,#"))
            if kind == "(directory)":
                queue.append(child_url(location, name))
                continue
            if kind != "(regular)":
                continue
            years = sorted(set(YEARS.findall(path)))
            records.append({
                "path": path,
                "name": PurePosixPath(path).name,
                "extension": PurePosixPath(path).suffix.lower(),
                "size_bytes": size,
                "years_detected": ",".join(years),
                "keyword_match": int(bool(KEYWORDS.search(path))),
            })

    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "path", "name", "extension", "size_bytes", "years_detected", "keyword_match"
        ])
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda row: str(row["path"]).lower()))
    print(f"directories={len(seen)} files={len(records)} pending={len(queue)} output={args.output}")


if __name__ == "__main__":
    main()
