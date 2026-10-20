from __future__ import annotations

import csv
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from generar_reportes_energia_15min_enero import (
    RATIO_LINEA_PANDO,
    build_ml,
    build_pando,
    read_smec,
    summarize_daily,
    summarize_kpis,
    write_csv,
    write_xlsx,
)


ZIP_PATH = Path("/home/jdm/Documents/Reportes de Generacion/Febrero 2026.zip")
OUT_DIR = Path(__file__).with_name("reportes_energia_15min_febrero_2026")
EXPECTED_PANDO = Path("/home/jdm/Downloads/Reportes_de_Operaciones_Febrero_2026/Operaciones_EISA_Energia_Pando_Febrero_2026_completo.xlsx")
EXPECTED_ML = Path("/home/jdm/Downloads/Reportes_de_Operaciones_Febrero_2026/Operaciones_EISA_Energia_Montelirio_Febrero_2026_completo.xlsx")


def parse_balance_datetime(fecha: str, hora: str) -> datetime | None:
    text = f"{fecha.strip()} {hora.strip()}"
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def read_balance_csv(path: Path) -> dict[datetime, dict[str, str]]:
    text = path.read_bytes().replace(b"\x00", b"").decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines(), delimiter=";")
    rows: dict[datetime, dict[str, str]] = {}
    for row in reader:
        timestamp = parse_balance_datetime(row.get("FECHA", ""), row.get("HORA", ""))
        if timestamp is not None and timestamp not in rows:
            rows[timestamp] = row
    return rows


def safe_delta(readings: dict[datetime, dict[str, str]], timestamp: datetime, tag: str, max_mwh: float = 100.0) -> float | None:
    from generar_reportes_energia_15min_enero import delta

    value = delta(readings, timestamp, tag)
    if value is None:
        return None
    if value < 0 or value > max_mwh:
        return None
    return value


def shift_rows_to_month(rows: list[dict[str, object]], year: int, month: int, days: int) -> list[dict[str, object]]:
    """build_* in the enero module emits a 31-day Jan grid; remap formulas to February grid."""
    # This function is intentionally unused. It documents why we use the local builders below.
    return rows


def build_pando_febrero(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float]) -> list[dict[str, object]]:
    from generar_reportes_energia_15min_enero import delta, delta_smec, excel_serial, zero_if_none

    rows = []
    start = datetime(2026, 2, 1, 0, 0)
    for index in range(28 * 96):
        timestamp = start + timedelta(minutes=15 * index)
        bruta_u1 = safe_delta(balance, timestamp, "G1_JQ_GEN_P_EXP")
        bruta_u2 = safe_delta(balance, timestamp, "G2_JQ_GEN_P_EXP")
        consumo_u1 = safe_delta(balance, timestamp, "G1_JQ_UAB_P_EXP", max_mwh=10.0)
        consumo_u2 = safe_delta(balance, timestamp, "G2_JQ_UAB_P_EXP", max_mwh=10.0)
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


def build_ml_febrero(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float]) -> list[dict[str, object]]:
    from generar_reportes_energia_15min_enero import delta, delta_smec, excel_serial

    rows = []
    start = datetime(2026, 2, 1, 0, 0)
    for index in range(28 * 96):
        timestamp = start + timedelta(minutes=15 * index)
        brutas = [safe_delta(balance, timestamp, f"G{i}_JQ_GEN_P_EXP") for i in (1, 2, 3)]
        netas = [safe_delta(balance, timestamp, f"G{i}_JQ_LIN_P_EXP") for i in (1, 2, 3)]
        consumos = [safe_delta(balance, timestamp, f"G{i}_JQ_UAB_P_EXP", max_mwh=10.0) for i in (1, 2, 3)]
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
    temp_dir = Path(tempfile.mkdtemp(prefix="energia_15min_febrero_"))
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir()
    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            archive.extractall(temp_dir)

        pdo_balance = read_balance_csv(next(temp_dir.rglob("Balance de energía/Balance de energía PDO Febrero 2026.csv")))
        ml_balance = read_balance_csv(next(temp_dir.rglob("Balance de energía/Balance Energia ML Febrero 2026.csv")))
        primavera = read_smec(next(temp_dir.rglob("SMEC/SMEC FEBRERO 2026 SE PRIMAVERA.csv")))
        el_alto = read_smec(next(temp_dir.rglob("SMEC/SMEC FEBRERO 2026 SE EL ALTO.csv")))

        pando_rows = build_pando_febrero(pdo_balance, primavera)
        ml_rows = build_ml_febrero(ml_balance, el_alto)

        pando_columns = [
            "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta Total (MWh)",
            "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta Total (MWh)",
            "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo Total (MWh)",
            "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad",
        ]
        ml_columns = [
            "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta U3 (MWh)", "Energía Bruta Total (MWh)",
            "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta U3 (MWh)", "Energía Neta Total (MWh)",
            "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo U3 (MWh)", "Consumo Total (MWh)",
            "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad",
        ]
        pando_daily = summarize_daily(pando_rows, pando_columns[1:-1])
        ml_daily = summarize_daily(ml_rows, ml_columns[1:-1])
        pando_kpis = summarize_kpis(pando_rows, "PDO", ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"])
        ml_kpis = summarize_kpis(ml_rows, "ML", ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"])

        write_csv(OUT_DIR / "Pando_Consolidado_15min_Febrero_2026.csv", pando_rows, pando_columns)
        write_csv(OUT_DIR / "Montelirio_Consolidado_15min_Febrero_2026.csv", ml_rows, ml_columns)
        write_xlsx(OUT_DIR / "Operaciones_EISA_Energia_Pando_Febrero_2026_15min_generado.xlsx", [
            ("Diario", "Reporte de Energía • Pando • Febrero 2026", pando_daily, ["Fecha"] + pando_columns[1:-1] + ["Intervalos no medidos"]),
            ("Resumen", "Resumen • Pando • Febrero 2026", pando_kpis, ["KPI", "Valor"]),
            ("Consolidado", "Consolidado 15-min • Pando • Febrero 2026", pando_rows, pando_columns),
        ])
        write_xlsx(OUT_DIR / "Operaciones_EISA_Energia_Montelirio_Febrero_2026_15min_generado.xlsx", [
            ("Diario", "Reporte de Energía • Montelirio • Febrero 2026", ml_daily, ["Fecha"] + ml_columns[1:-1] + ["Intervalos no medidos"]),
            ("Resumen", "Resumen • Montelirio • Febrero 2026", ml_kpis, ["KPI", "Valor"]),
            ("Consolidado", "Consolidado 15-min • Montelirio • Febrero 2026", ml_rows, ml_columns),
        ])

        print(OUT_DIR)
        print("Pando", pando_kpis[:7])
        print("Montelirio", ml_kpis[:7])
        print("Calidad Pando", {q: sum(1 for row in pando_rows if row["Calidad"] == q) for q in sorted({row["Calidad"] for row in pando_rows})})
        print("Calidad Montelirio", {q: sum(1 for row in ml_rows if row["Calidad"] == q) for q in sorted({row["Calidad"] for row in ml_rows})})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
