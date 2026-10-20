from __future__ import annotations

import argparse
import calendar
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from generar_reportes_energia_15min_enero import (
    RATIO_LINEA_PANDO,
    delta_smec,
    excel_serial,
    read_balance,
    read_smec,
    summarize_daily,
    summarize_kpis,
    write_csv,
    write_xlsx,
    zero_if_none,
)
from generar_reportes_energia_15min_febrero import read_balance_csv, safe_delta


PANDO_COLUMNS = [
    "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta Total (MWh)",
    "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta Total (MWh)",
    "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo Total (MWh)",
    "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad",
]

ML_COLUMNS = [
    "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta U3 (MWh)", "Energía Bruta Total (MWh)",
    "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta U3 (MWh)", "Energía Neta Total (MWh)",
    "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo U3 (MWh)", "Consumo Total (MWh)",
    "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad",
]


def norm(text: str) -> str:
    return (
        text.lower()
        .replace("í", "i")
        .replace("ì", "i")
        .replace("б", "i")
        .replace("é", "e")
        .replace("ó", "o")
        .replace("в", "o")
    )


def find_one(root: Path, contains: list[str], suffixes: tuple[str, ...]) -> Path:
    candidates = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        name = norm(str(path))
        if all(token in name for token in contains):
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No encontre archivo con tokens {contains}")
    return sorted(candidates, key=lambda item: len(str(item)))[0]


def read_balance_any(path: Path, plant: str) -> dict[datetime, dict[str, str]]:
    if path.suffix.lower() == ".csv":
        return read_balance_csv(path)
    return read_balance(path, plant)


def build_pando(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float], year: int, month: int) -> list[dict[str, object]]:
    rows = []
    start = datetime(year, month, 1)
    for index in range(calendar.monthrange(year, month)[1] * 96):
        timestamp = start + timedelta(minutes=15 * index)
        bruta_u1 = safe_delta(balance, timestamp, "G1_JQ_GEN_P_EXP")
        bruta_u2 = safe_delta(balance, timestamp, "G2_JQ_GEN_P_EXP")
        consumo_u1 = safe_delta(balance, timestamp, "G1_JQ_UAB_P_EXP", max_mwh=10)
        consumo_u2 = safe_delta(balance, timestamp, "G2_JQ_UAB_P_EXP", max_mwh=10)
        se = delta_smec(smec, timestamp)
        bruta_total = None if bruta_u1 is None or bruta_u2 is None else bruta_u1 + bruta_u2
        consumo_total = None if consumo_u1 is None or consumo_u2 is None else consumo_u1 + consumo_u2
        neta_total = None if se is None else se / (1 - RATIO_LINEA_PANDO)
        if bruta_total and neta_total is not None:
            neta_u1 = zero_if_none(bruta_u1) * neta_total / bruta_total
            neta_u2 = zero_if_none(bruta_u2) * neta_total / bruta_total
        else:
            neta_u1 = None
            neta_u2 = None
        perdida_interna = None if None in (bruta_total, neta_total, consumo_total) else bruta_total - neta_total - consumo_total
        perdida_linea = None if None in (neta_total, se) else neta_total - se
        perdida_total = None if None in (perdida_interna, perdida_linea) else perdida_interna + perdida_linea
        rows.append({
            "Timestamp": excel_serial(timestamp),
            "Energía Bruta U1 (MWh)": bruta_u1,
            "Energía Bruta U2 (MWh)": bruta_u2,
            "Energía Bruta Total (MWh)": bruta_total,
            "Energía Neta U1 (MWh)": neta_u1,
            "Energía Neta U2 (MWh)": neta_u2,
            "Energía Neta Total (MWh)": neta_total,
            "Consumo U1 (MWh)": consumo_u1,
            "Consumo U2 (MWh)": consumo_u2,
            "Consumo Total (MWh)": consumo_total,
            "SE Primavera (MWh)": se,
            "Pérdida interna (MWh)": perdida_interna,
            "Pérdida en la línea (MWh)": perdida_linea,
            "Pérdida total (MWh)": perdida_total,
            "Calidad": "hueco" if any(value is None for value in (bruta_total, consumo_total, se)) else "medido",
        })
    return rows


def build_ml(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float], year: int, month: int) -> list[dict[str, object]]:
    rows = []
    start = datetime(year, month, 1)
    for index in range(calendar.monthrange(year, month)[1] * 96):
        timestamp = start + timedelta(minutes=15 * index)
        brutas = [safe_delta(balance, timestamp, f"G{i}_JQ_GEN_P_EXP") for i in (1, 2, 3)]
        netas = [safe_delta(balance, timestamp, f"G{i}_JQ_LIN_P_EXP") for i in (1, 2, 3)]
        consumos = [safe_delta(balance, timestamp, f"G{i}_JQ_UAB_P_EXP", max_mwh=10) for i in (1, 2, 3)]
        se = delta_smec(smec, timestamp)
        bruta_total = None if any(value is None for value in brutas) else sum(brutas)  # type: ignore[arg-type]
        neta_total = None if any(value is None for value in netas) else sum(netas)  # type: ignore[arg-type]
        consumo_total = None if any(value is None for value in consumos) else sum(consumos)  # type: ignore[arg-type]
        perdida_interna = None if None in (bruta_total, neta_total, consumo_total) else bruta_total - neta_total - consumo_total
        perdida_linea = None if None in (neta_total, se) else neta_total - se
        perdida_total = None if None in (perdida_interna, perdida_linea) else perdida_interna + perdida_linea
        rows.append({
            "Timestamp": excel_serial(timestamp),
            "Energía Bruta U1 (MWh)": brutas[0],
            "Energía Bruta U2 (MWh)": brutas[1],
            "Energía Bruta U3 (MWh)": brutas[2],
            "Energía Bruta Total (MWh)": bruta_total,
            "Energía Neta U1 (MWh)": netas[0],
            "Energía Neta U2 (MWh)": netas[1],
            "Energía Neta U3 (MWh)": netas[2],
            "Energía Neta Total (MWh)": neta_total,
            "Consumo U1 (MWh)": consumos[0],
            "Consumo U2 (MWh)": consumos[1],
            "Consumo U3 (MWh)": consumos[2],
            "Consumo Total (MWh)": consumo_total,
            "SE El Alto (MWh)": se,
            "Pérdida interna (MWh)": perdida_interna,
            "Pérdida en la línea (MWh)": perdida_linea,
            "Pérdida total (MWh)": perdida_total,
            "Calidad": "hueco" if any(value is None for value in (bruta_total, neta_total, consumo_total, se)) else "medido",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera reportes de energia 15-min por mes.")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--month-title", required=True)
    parser.add_argument("--period-slug", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    temp_dir = Path(tempfile.mkdtemp(prefix=f"energia_15min_{args.period_slug.lower()}_"))
    if args.out_dir.exists():
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir()
    try:
        with zipfile.ZipFile(args.zip) as archive:
            archive.extractall(temp_dir)

        try:
            pdo_path = find_one(temp_dir, ["balance de energi", "pdo"], (".csv", ".xlsx"))
        except FileNotFoundError:
            # Algunos meses identifican Pando como PN en lugar de PDO.
            pdo_path = find_one(temp_dir, ["balance de energi", "pn"], (".csv", ".xlsx"))
        pdo_balance = read_balance_any(pdo_path, "PDO")
        ml_balance = read_balance_any(find_one(temp_dir, ["balance de energi", "ml"], (".csv", ".xlsx")), "ML")
        try:
            primavera_path = find_one(temp_dir, ["smec", "primavera"], (".csv",))
        except FileNotFoundError:
            primavera_path = find_one(temp_dir, ["smec", "pando"], (".csv",))
        try:
            el_alto_path = find_one(temp_dir, ["smec", "alto"], (".csv",))
        except FileNotFoundError:
            try:
                el_alto_path = find_one(temp_dir, ["smec", "ml"], (".csv",))
            except FileNotFoundError:
                el_alto_path = find_one(temp_dir, ["smec", "lirio"], (".csv",))
        primavera = read_smec(primavera_path)
        el_alto = read_smec(el_alto_path)

        pando_rows = build_pando(pdo_balance, primavera, args.year, args.month)
        ml_rows = build_ml(ml_balance, el_alto, args.year, args.month)

        write_csv(args.out_dir / f"Pando_Consolidado_15min_{args.period_slug}.csv", pando_rows, PANDO_COLUMNS)
        write_csv(args.out_dir / f"Montelirio_Consolidado_15min_{args.period_slug}.csv", ml_rows, ML_COLUMNS)
        write_xlsx(args.out_dir / f"Operaciones_EISA_Energia_Pando_{args.period_slug}_15min_generado.xlsx", [
            ("Diario", f"Reporte de Energía • Pando • {args.month_title}", summarize_daily(pando_rows, PANDO_COLUMNS[1:-1]), ["Fecha"] + PANDO_COLUMNS[1:-1] + ["Intervalos no medidos"]),
            ("Resumen", f"Resumen • Pando • {args.month_title}", summarize_kpis(pando_rows, "PDO", ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"]), ["KPI", "Valor"]),
            ("Consolidado", f"Consolidado 15-min • Pando • {args.month_title}", pando_rows, PANDO_COLUMNS),
        ])
        write_xlsx(args.out_dir / f"Operaciones_EISA_Energia_Montelirio_{args.period_slug}_15min_generado.xlsx", [
            ("Diario", f"Reporte de Energía • Montelirio • {args.month_title}", summarize_daily(ml_rows, ML_COLUMNS[1:-1]), ["Fecha"] + ML_COLUMNS[1:-1] + ["Intervalos no medidos"]),
            ("Resumen", f"Resumen • Montelirio • {args.month_title}", summarize_kpis(ml_rows, "ML", ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"]), ["KPI", "Valor"]),
            ("Consolidado", f"Consolidado 15-min • Montelirio • {args.month_title}", ml_rows, ML_COLUMNS),
        ])
        print(args.out_dir)
        print("Pando calidad", {q: sum(1 for row in pando_rows if row["Calidad"] == q) for q in sorted({row["Calidad"] for row in pando_rows})})
        print("ML calidad", {q: sum(1 for row in ml_rows if row["Calidad"] == q) for q in sorted({row["Calidad"] for row in ml_rows})})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
