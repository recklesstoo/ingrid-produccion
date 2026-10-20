#!/usr/bin/env python3
"""Orquestador determinista para ingestar un ZIP mensual de generación."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


MONTHS = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def run(command: list[str], log: Path) -> None:
    with log.open("a", encoding="utf-8") as handle:
        handle.write("\n$ " + " ".join(command) + "\n")
        result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(f"Falló el paso: {command[1] if len(command) > 1 else command[0]} (rc={result.returncode})")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta mensual validada de generación EISA.")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--work-root", type=Path, default=Path("work"))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    if not args.zip.is_file():
        raise SystemExit(f"No existe el ZIP: {args.zip}")
    if args.month not in MONTHS:
        raise SystemExit("El mes debe estar entre 1 y 12")

    root = Path(__file__).resolve().parent
    slug = f"{MONTHS[args.month]}_{args.year}"
    run_root = args.work_root / slug.lower()
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    base_dir = run_root / "base"
    od_dir = run_root / "operacion_diaria"
    corrected_dir = run_root / "validado_corregido"
    log = run_root / "ingesta.log"

    run([
        args.python, str(root / "generar_reportes_energia_15min_mensual.py"),
        "--zip", str(args.zip), "--year", str(args.year), "--month", str(args.month),
        "--month-title", f"{MONTHS[args.month]} {args.year}", "--period-slug", slug,
        "--out-dir", str(base_dir),
    ], log)
    run([
        args.python, str(root / "crear_maestro_operacion_diaria.py"),
        "--zip", str(args.zip), "--out-dir", str(od_dir),
    ], log)

    od_candidates = sorted(od_dir.glob("*filtrado*.csv"))
    if not od_candidates:
        od_candidates = sorted(od_dir.glob("*.csv"))
    if not od_candidates:
        raise RuntimeError("El maestro de Operación Diaria no produjo CSV")
    pando = base_dir / f"Pando_Consolidado_15min_{slug}.csv"
    montelirio = base_dir / f"Montelirio_Consolidado_15min_{slug}.csv"
    run([
        args.python, str(root / "validar_corregir_energia.py"),
        "--pando", str(pando), "--ml", str(montelirio), "--od", str(od_candidates[0]),
        "--out-dir", str(corrected_dir), "--month-title", f"{MONTHS[args.month]} {args.year}",
        "--period-slug", slug,
    ], log)
    run([
        args.python, str(root / "ingrid_base_analitica.py"),
        "--work-root", str(args.work_root),
        "--db", str(args.work_root.parent / "data" / "ingrid_analitica.sqlite"),
    ], log)

    outputs = sorted(str(path.relative_to(run_root)) for path in corrected_dir.iterdir() if path.is_file())
    manifest = {
        "estado": "completado",
        "periodo": f"{args.year}-{args.month:02d}",
        "zip": str(args.zip),
        "sha256": sha256(args.zip),
        "salida": str(corrected_dir),
        "archivos": outputs,
        "reglas": ["SMEC confiable", "rollover corregido por delta_smec", "operacion_diaria para unidades en linea", "SCADA inconsistente estimado"],
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
    }
    (run_root / "manifiesto.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
