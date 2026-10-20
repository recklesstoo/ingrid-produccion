#!/usr/bin/env python3
"""Carga reportes corregidos de Ingrid en una base SQLite consultable."""
from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
from pathlib import Path


def number(value: str | None) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_csv(db: sqlite3.Connection, path: Path, plant: str, period: str) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = "energy_15min"
    count = 0
    for row in rows:
        db.execute(
            """INSERT OR REPLACE INTO energy_15min
            (plant, period, timestamp_serial, gross_total, net_total, consumption,
             smec, internal_loss, line_loss, total_loss, quality, method, reason, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plant, period, number(row.get("Timestamp")), number(row.get("Energía Bruta Total (MWh)")),
             number(row.get("Energía Neta Total (MWh)")), number(row.get("Consumo Total (MWh)")),
             number(row.get("SE Primavera (MWh)") or row.get("SE El Alto (MWh)")),
             number(row.get("Pérdida interna (MWh)")), number(row.get("Pérdida en la línea (MWh)")),
             number(row.get("Pérdida total (MWh)")), row.get("Calidad"), row.get("Metodo"),
             row.get("Motivo"), str(path)),
        )
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, default=Path("work"))
    parser.add_argument("--db", type=Path, default=Path("data/ingrid_analitica.sqlite"))
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS energy_15min (
            plant TEXT NOT NULL, period TEXT NOT NULL, timestamp_serial REAL NOT NULL,
            gross_total REAL, net_total REAL, consumption REAL, smec REAL,
            internal_loss REAL, line_loss REAL, total_loss REAL,
            quality TEXT, method TEXT, reason TEXT, source_file TEXT,
            PRIMARY KEY (plant, period, timestamp_serial)
        );
        CREATE INDEX IF NOT EXISTS idx_energy_period ON energy_15min(period, plant);
        CREATE INDEX IF NOT EXISTS idx_energy_quality ON energy_15min(quality);
        """)
        loaded = 0
        for path in sorted(args.work_root.glob("*/validado_corregido/*Consolidado*csv")):
            name = path.name.lower()
            plant = "Pando" if "pando" in name else "Montelirio"
            period = path.parent.parent.name
            loaded += load_csv(db, path, plant, period)
        print(f"cargadas={loaded} db={args.db}")


if __name__ == "__main__":
    main()
