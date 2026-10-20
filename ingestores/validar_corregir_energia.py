from __future__ import annotations

import argparse
import csv
import shutil
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from generar_reportes_energia_15min_enero import RATIO_LINEA_PANDO, summarize_daily, summarize_kpis, write_csv, write_xlsx


PANDO_COLUMNS = [
    "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta Total (MWh)",
    "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta Total (MWh)",
    "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo Total (MWh)",
    "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad", "Metodo", "Motivo",
]

ML_COLUMNS = [
    "Timestamp", "Energía Bruta U1 (MWh)", "Energía Bruta U2 (MWh)", "Energía Bruta U3 (MWh)", "Energía Bruta Total (MWh)",
    "Energía Neta U1 (MWh)", "Energía Neta U2 (MWh)", "Energía Neta U3 (MWh)", "Energía Neta Total (MWh)",
    "Consumo U1 (MWh)", "Consumo U2 (MWh)", "Consumo U3 (MWh)", "Consumo Total (MWh)",
    "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)", "Calidad", "Metodo", "Motivo",
]

UNIT_MAP = {
    "PDO": {"U1": "PDOG1", "U2": "PDOG2"},
    "ML": {"U1": "MLG1", "U2": "MLG2", "U3": "MLG3"},
}


def excel_dt(serial: object) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=float(serial))


def parse_float(value: object) -> float | None:
    text = str(value or "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_energy_csv(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            converted: dict[str, object] = {}
            for key, value in row.items():
                if key in {"Calidad", "Metodo", "Motivo"}:
                    converted[key] = value
                else:
                    converted[key] = parse_float(value) if key != "Timestamp" else float(value)
                    if converted[key] is None:
                        converted[key] = ""
            converted.setdefault("Metodo", "medicion_directa")
            converted.setdefault("Motivo", "")
            rows.append(converted)
    return rows


def read_online_map(path: Path) -> dict[tuple[str, str, datetime], bool]:
    online: dict[tuple[str, str, datetime], bool] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                timestamp = datetime.strptime(row["timestamp_inicio"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            online[(row["planta_id"], row["unidad_id"], timestamp)] = row["en_linea"] == "1"
    return online


def online_units(online: dict[tuple[str, str, datetime], bool], plant: str, timestamp: datetime) -> list[str]:
    hour = timestamp.replace(minute=0, second=0, microsecond=0)
    return [unit for unit, od_unit in UNIT_MAP[plant].items() if online.get((plant, od_unit, hour), False)]


def median(values: list[float], default: float) -> float:
    clean = [value for value in values if value == value]
    return statistics.median(clean) if clean else default


def median_with_floor(values: list[float], default: float, floor: float, ceiling: float | None = None) -> float:
    value = median(values, default)
    if value < floor:
        return default
    if ceiling is not None and value > ceiling:
        return default
    return value


def measured_good_pando(row: dict[str, object]) -> bool:
    bruta = parse_float(row.get("Energía Bruta Total (MWh)"))
    neta = parse_float(row.get("Energía Neta Total (MWh)"))
    consumo = parse_float(row.get("Consumo Total (MWh)"))
    se = parse_float(row.get("SE Primavera (MWh)"))
    if None in (bruta, neta, consumo, se):
        return False
    if bruta <= 0 or neta <= 0 or se <= 0:
        return False
    if bruta < neta * 0.85 or bruta > neta * 1.25:
        return False
    return True


def measured_good_ml(row: dict[str, object]) -> bool:
    bruta = parse_float(row.get("Energía Bruta Total (MWh)"))
    neta = parse_float(row.get("Energía Neta Total (MWh)"))
    consumo = parse_float(row.get("Consumo Total (MWh)"))
    se = parse_float(row.get("SE El Alto (MWh)"))
    if None in (bruta, neta, consumo, se):
        return False
    if bruta <= 0 or neta <= 0 or se <= 0:
        return False
    if neta < se * 0.85 or neta > se * 1.20:
        return False
    if bruta < neta * 0.95 or bruta > neta * 1.08:
        return False
    return True


def pando_profile(rows: list[dict[str, object]]) -> dict[str, object]:
    good = [row for row in rows if measured_good_pando(row)]
    internal_ratios = []
    consumption_ratios = []
    shares = {"U1": [], "U2": []}
    for row in good:
        bruta = parse_float(row["Energía Bruta Total (MWh)"]) or 0
        neta = parse_float(row["Energía Neta Total (MWh)"]) or 0
        consumo = parse_float(row["Consumo Total (MWh)"]) or 0
        if neta > 0:
            internal_ratios.append(max(0.0, (bruta - neta - consumo) / neta))
            consumption_ratios.append(max(0.0, consumo / neta))
        if bruta > 0:
            for unit in shares:
                shares[unit].append((parse_float(row[f"Energía Bruta {unit} (MWh)"]) or 0) / bruta)
    return {
        "internal_ratio": median_with_floor(internal_ratios, 0.0115, 0.0010, 0.0400),
        "consumption_ratio": median_with_floor(consumption_ratios, 0.0040, 0.0005, 0.0200),
        "share": {unit: median(values, 1 / len(shares)) for unit, values in shares.items()},
        "good_intervals": len(good),
    }


def ml_profile(rows: list[dict[str, object]]) -> dict[str, object]:
    good = [row for row in rows if measured_good_ml(row)]
    line_ratios = []
    internal_ratios = []
    consumption_ratios = []
    shares = {"U1": [], "U2": [], "U3": []}
    for row in good:
        bruta = parse_float(row["Energía Bruta Total (MWh)"]) or 0
        neta = parse_float(row["Energía Neta Total (MWh)"]) or 0
        consumo = parse_float(row["Consumo Total (MWh)"]) or 0
        se = parse_float(row["SE El Alto (MWh)"]) or 0
        if neta > 0:
            line_ratios.append(max(0.0, (neta - se) / neta))
            internal_ratios.append(max(0.0, (bruta - neta - consumo) / neta))
            consumption_ratios.append(max(0.0, consumo / neta))
            for unit in shares:
                shares[unit].append((parse_float(row[f"Energía Neta {unit} (MWh)"]) or 0) / neta)
    return {
        "line_ratio": median_with_floor(line_ratios, 0.00628, 0.0010, 0.0300),
        "internal_ratio": median_with_floor(internal_ratios, 0.00785, 0.0010, 0.0300),
        "consumption_ratio": median_with_floor(consumption_ratios, 0.0060, 0.0005, 0.0200),
        "share": {unit: median(values, 1 / len(shares)) for unit, values in shares.items()},
        "good_intervals": len(good),
    }


def normalize_shares(profile_shares: dict[str, float], active_units: list[str]) -> dict[str, float]:
    if not active_units:
        return {}
    total = sum(profile_shares.get(unit, 0.0) for unit in active_units)
    if total <= 0:
        return {unit: 1.0 / len(active_units) for unit in active_units}
    return {unit: profile_shares.get(unit, 0.0) / total for unit in active_units}


def needs_pando_estimate(row: dict[str, object]) -> tuple[bool, str]:
    if not measured_good_pando(row):
        return True, "scada_invalido_o_incompleto"
    return False, ""


def needs_ml_estimate(row: dict[str, object]) -> tuple[bool, str]:
    if not measured_good_ml(row):
        return True, "scada_redondeado_incompleto_o_inconsistente_con_smec"
    return False, ""


def fill_missing_smec(rows: list[dict[str, object]], column: str, index: int) -> tuple[float | None, str]:
    """Usa la lectura SMEC válida más cercana para completar un único hueco."""
    for distance in range(1, len(rows)):
        for candidate in (index - distance, index + distance):
            if 0 <= candidate < len(rows):
                value = parse_float(rows[candidate].get(column))
                if value is not None and value > 0:
                    return value, "smec_faltante_estimado_intervalo_vecino"
    return None, "smec_faltante_sin_referencia"


def correct_pando(rows: list[dict[str, object]], online: dict[tuple[str, str, datetime], bool]) -> tuple[int, dict[str, object]]:
    profile = pando_profile(rows)
    corrected = 0
    for index, row in enumerate(rows):
        timestamp = excel_dt(row["Timestamp"])
        should_estimate, reason = needs_pando_estimate(row)
        if not should_estimate:
            row["Calidad"] = "medido"
            row["Metodo"] = "medicion_directa"
            row["Motivo"] = ""
            continue
        se = parse_float(row.get("SE Primavera (MWh)"))
        if se is None:
            se, smec_reason = fill_missing_smec(rows, "SE Primavera (MWh)", index)
            reason = smec_reason
            if se is not None:
                row["SE Primavera (MWh)"] = se
        active = online_units(online, "PDO", timestamp)
        if se is None or se <= 0 or not active:
            row["Calidad"] = "hueco"
            row["Metodo"] = "sin_estimacion"
            row["Motivo"] = reason or "sin_smec_o_sin_unidades_en_linea"
            continue
        neta_total = se / (1 - RATIO_LINEA_PANDO)
        consumo_total = neta_total * float(profile["consumption_ratio"])
        bruta_total = neta_total + consumo_total + (neta_total * float(profile["internal_ratio"]))
        shares = normalize_shares(profile["share"], active)  # type: ignore[arg-type]
        for unit in ("U1", "U2"):
            share = shares.get(unit, 0.0)
            row[f"Energía Bruta {unit} (MWh)"] = bruta_total * share
            row[f"Energía Neta {unit} (MWh)"] = neta_total * share
            row[f"Consumo {unit} (MWh)"] = consumo_total * share
        row["Energía Bruta Total (MWh)"] = bruta_total
        row["Energía Neta Total (MWh)"] = neta_total
        row["Consumo Total (MWh)"] = consumo_total
        row["Pérdida interna (MWh)"] = bruta_total - neta_total - consumo_total
        row["Pérdida en la línea (MWh)"] = neta_total - se
        row["Pérdida total (MWh)"] = row["Pérdida interna (MWh)"] + row["Pérdida en la línea (MWh)"]
        row["Calidad"] = "estimado_smec_operacion_diaria"
        row["Metodo"] = "smec_primavera_ratio_perdidas_y_unidades_en_linea"
        row["Motivo"] = reason
        corrected += 1
    return corrected, profile


def correct_ml(rows: list[dict[str, object]], online: dict[tuple[str, str, datetime], bool]) -> tuple[int, dict[str, object]]:
    profile = ml_profile(rows)
    corrected = 0
    for index, row in enumerate(rows):
        timestamp = excel_dt(row["Timestamp"])
        should_estimate, reason = needs_ml_estimate(row)
        if not should_estimate:
            row["Calidad"] = "medido"
            row["Metodo"] = "medicion_directa"
            row["Motivo"] = ""
            continue
        se = parse_float(row.get("SE El Alto (MWh)"))
        if se is None:
            se, smec_reason = fill_missing_smec(rows, "SE El Alto (MWh)", index)
            reason = smec_reason
            if se is not None:
                row["SE El Alto (MWh)"] = se
        active = online_units(online, "ML", timestamp)
        if se is None or se <= 0 or not active:
            row["Calidad"] = "hueco"
            row["Metodo"] = "sin_estimacion"
            row["Motivo"] = reason or "sin_smec_o_sin_unidades_en_linea"
            continue
        line_ratio = float(profile["line_ratio"])
        neta_total = se / (1 - line_ratio)
        consumo_total = neta_total * float(profile["consumption_ratio"])
        bruta_total = neta_total + consumo_total + (neta_total * float(profile["internal_ratio"]))
        shares = normalize_shares(profile["share"], active)  # type: ignore[arg-type]
        for unit in ("U1", "U2", "U3"):
            share = shares.get(unit, 0.0)
            row[f"Energía Bruta {unit} (MWh)"] = bruta_total * share
            row[f"Energía Neta {unit} (MWh)"] = neta_total * share
            row[f"Consumo {unit} (MWh)"] = consumo_total * share
        row["Energía Bruta Total (MWh)"] = bruta_total
        row["Energía Neta Total (MWh)"] = neta_total
        row["Consumo Total (MWh)"] = consumo_total
        row["Pérdida interna (MWh)"] = bruta_total - neta_total - consumo_total
        row["Pérdida en la línea (MWh)"] = neta_total - se
        row["Pérdida total (MWh)"] = row["Pérdida interna (MWh)"] + row["Pérdida en la línea (MWh)"]
        row["Calidad"] = "estimado_smec_operacion_diaria"
        row["Metodo"] = "smec_el_alto_mediana_perdidas_y_unidades_en_linea"
        row["Motivo"] = reason
        corrected += 1
    return corrected, profile


def quality_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        quality = str(row.get("Calidad", ""))
        counts[quality] = counts.get(quality, 0) + 1
    return counts


def metric_totals(rows: list[dict[str, object]], columns: list[str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for column in columns:
        totals[column] = sum(parse_float(row.get(column)) or 0.0 for row in rows)
    return totals


def write_report(
    out_dir: Path,
    plant: str,
    rows: list[dict[str, object]],
    columns: list[str],
    profile: dict[str, object],
    month_title: str,
    period_slug: str,
) -> None:
    if plant == "PDO":
        xlsx_name = f"Operaciones_EISA_Energia_Pando_{period_slug}_validado_corregido.xlsx"
        csv_name = f"Pando_Consolidado_15min_{period_slug}_validado_corregido.csv"
        title = "Pando"
        kpi_columns = ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE Primavera (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"]
    else:
        xlsx_name = f"Operaciones_EISA_Energia_Montelirio_{period_slug}_validado_corregido.xlsx"
        csv_name = f"Montelirio_Consolidado_15min_{period_slug}_validado_corregido.csv"
        title = "Montelirio"
        kpi_columns = ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE El Alto (MWh)", "Pérdida interna (MWh)", "Pérdida en la línea (MWh)", "Pérdida total (MWh)"]
    write_csv(out_dir / csv_name, rows, columns)
    summary = summarize_kpis(rows, plant, kpi_columns)
    summary.extend([
        {"KPI": "Intervalos medidos", "Valor": quality_counts(rows).get("medido", 0)},
        {"KPI": "Intervalos estimados", "Valor": quality_counts(rows).get("estimado_smec_operacion_diaria", 0)},
        {"KPI": "Perfil intervalos buenos", "Valor": profile.get("good_intervals", 0)},
        {"KPI": "Nota corrección", "Valor": "SMEC se toma como confiable; SCADA inválido se estima con Operación Diaria y medianas de pérdidas."},
    ])
    write_xlsx(out_dir / xlsx_name, [
        ("Diario", f"Reporte de Energía • {title} • {month_title}", summarize_daily(rows, columns[1:-3]), ["Fecha"] + columns[1:-3] + ["Intervalos no medidos"]),
        ("Resumen", f"Resumen • {title} • {month_title}", summary, ["KPI", "Valor"]),
        ("Consolidado", f"Consolidado 15-min • {title} • {month_title}", rows, columns),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida y corrige energia 15-min usando SMEC confiable y Operacion Diaria.")
    parser.add_argument("--pando", type=Path, default=Path("reportes_energia_15min_febrero_2026/Pando_Consolidado_15min_Febrero_2026.csv"))
    parser.add_argument("--ml", type=Path, default=Path("reportes_energia_15min_febrero_2026/Montelirio_Consolidado_15min_Febrero_2026.csv"))
    parser.add_argument("--od", type=Path, default=Path("maestro_operacion_diaria_febrero_2026/maestro_operacion_diaria_febrero_2026_filtrado_febrero.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("reportes_energia_15min_febrero_2026_validado_corregido"))
    parser.add_argument("--month-title", default="Febrero 2026")
    parser.add_argument("--period-slug", default="Febrero_2026")
    args = parser.parse_args()

    if args.out_dir.exists():
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir()
    online = read_online_map(args.od)
    pando_rows = read_energy_csv(args.pando)
    ml_rows = read_energy_csv(args.ml)
    pando_corrected, pando_prof = correct_pando(pando_rows, online)
    ml_corrected, ml_prof = correct_ml(ml_rows, online)

    write_report(args.out_dir, "PDO", pando_rows, PANDO_COLUMNS, pando_prof, args.month_title, args.period_slug)
    write_report(args.out_dir, "ML", ml_rows, ML_COLUMNS, ml_prof, args.month_title, args.period_slug)

    report = args.out_dir / f"validacion_correccion_{args.period_slug.lower()}.md"
    pando_totals = metric_totals(pando_rows, ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE Primavera (MWh)", "Pérdida total (MWh)"])
    ml_totals = metric_totals(ml_rows, ["Energía Bruta Total (MWh)", "Energía Neta Total (MWh)", "Consumo Total (MWh)", "SE El Alto (MWh)", "Pérdida total (MWh)"])
    lines = [
        f"# Validación y corrección energía {args.month_title}",
        "",
        "Regla aplicada: SMEC es confiable; SCADA inválido, en cero, hueco, redondeado o inconsistente se estima con SMEC + Operación Diaria + medianas de pérdidas de intervalos confiables.",
        "",
        "## Pando",
        f"- Intervalos corregidos: {pando_corrected}",
        f"- Calidad: `{quality_counts(pando_rows)}`",
        f"- Perfil: `{pando_prof}`",
        "",
        "| Métrica | Total |",
        "|---|---:|",
    ]
    lines.extend([f"| {key} | {value:.6f} |" for key, value in pando_totals.items()])
    lines.extend([
        "",
        "## Montelirio",
        f"- Intervalos corregidos: {ml_corrected}",
        f"- Calidad: `{quality_counts(ml_rows)}`",
        f"- Perfil: `{ml_prof}`",
        "",
        "| Métrica | Total |",
        "|---|---:|",
    ])
    lines.extend([f"| {key} | {value:.6f} |" for key, value in ml_totals.items()])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(args.out_dir)
    print(f"pando_corregidos={pando_corrected} calidad={quality_counts(pando_rows)}")
    print(f"ml_corregidos={ml_corrected} calidad={quality_counts(ml_rows)}")
    print(report)


if __name__ == "__main__":
    main()
