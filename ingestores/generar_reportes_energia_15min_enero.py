from __future__ import annotations

import csv
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape


ZIP_PATH = Path("/home/jdm/Documents/Reportes de Generacion/Enero 2026.zip")
OUT_DIR = Path(__file__).with_name("reportes_energia_15min_enero_2026")
RATIO_LINEA_PANDO = 0.00394

NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

PDO_COLUMNS = [
    "FECHA",
    "HORA",
    "G1_JQ_GEN_P_EXP",
    "G2_JQ_GEN_P_EXP",
    "JQ_LIN_P_EXP",
    "G1_JQ_UAB_P_EXP",
    "G2_JQ_UAB_P_EXP",
    "G1_JQ_UAB_P_IMP",
    "G2_JQ_UAB_P_IMP",
]


def excel_datetime(day_value: str, time_value: str) -> datetime | None:
    try:
        day = float(day_value)
        fraction = float(time_value)
    except (TypeError, ValueError):
        return None
    base = datetime(1899, 12, 30) + timedelta(days=day)
    return base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=round(fraction * 86400))


def excel_serial(dt: datetime) -> float:
    return (dt - datetime(1899, 12, 30)).total_seconds() / 86400


def parse_number(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text == "***":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def col_index(cell_ref: str) -> int:
    value = 0
    for ch in "".join(item for item in cell_ref if item.isalpha()).upper():
        value = value * 26 + ord(ch) - 64
    return value


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.findall(".//x:t", NS)) for item in root.findall("x:si", NS)]


def first_sheet_member(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: "xl/" + rel.attrib["Target"].lstrip("/")
        for rel in rels.findall("rel:Relationship", NS)
    }
    sheet = workbook.find("x:sheets/x:sheet", NS)
    if sheet is None:
        raise ValueError("Libro sin hojas")
    return rel_map[sheet.attrib[f"{{{NS['r']}}}id"]]


def read_balance(path: Path, plant: str) -> dict[datetime, dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        root = ElementTree.fromstring(archive.read(first_sheet_member(archive)))
        raw_rows: list[list[str]] = []
        for row_node in root.findall(".//x:sheetData/x:row", NS):
            values = {}
            for cell in row_node.findall("x:c", NS):
                value_node = cell.find("x:v", NS)
                raw = value_node.text if value_node is not None else ""
                if cell.attrib.get("t") == "s" and raw.isdigit():
                    raw = strings[int(raw)]
                values[col_index(cell.attrib.get("r", "A"))] = raw
            if values:
                raw_rows.append([values.get(idx, "") for idx in range(1, max(values) + 1)])
    if plant == "ML":
        header = raw_rows[0]
        data = raw_rows[1:]
    else:
        header = PDO_COLUMNS
        data = raw_rows
    out = {}
    for row in data:
        record = dict(zip(header, row + [""] * (len(header) - len(row))))
        timestamp = excel_datetime(record.get("FECHA", ""), record.get("HORA", ""))
        if timestamp is not None and timestamp not in out:
            out[timestamp] = record
    return out


def clean_csv_value(value: str) -> str:
    return value.replace("\x00", "").strip().strip('",; ')


def read_smec(path: Path, tag: str = "MWH3O") -> dict[datetime, float]:
    text = path.read_bytes().replace(b"\x00", b"").decode("latin1", errors="replace")
    lines = [line.replace(",;", ",") for line in text.splitlines()]
    record_header = next((idx for idx, line in enumerate(lines) if "RecNum" in line and "Date" in line), None)
    if record_header is None:
        return {}
    delimiter = "," if "," in lines[record_header] else ";"
    channel_line = next((line for line in lines[record_header + 1 : record_header + 6] if tag in line), "")
    channels = [clean_csv_value(value) for value in next(csv.reader([channel_line], delimiter=delimiter, skipinitialspace=True))]
    tag_index = channels.index(tag)
    readings = {}
    for line in lines[record_header + 1 :]:
        if not line or not line[0].isdigit():
            continue
        try:
            row = [clean_csv_value(value) for value in next(csv.reader([line], delimiter=delimiter, skipinitialspace=True))]
        except (csv.Error, StopIteration):
            continue
        try:
            float(row[4])
            channel_offset = 4
        except (ValueError, IndexError):
            channel_offset = 5
        if len(row) <= channel_offset + tag_index:
            continue
        try:
            timestamp = datetime.strptime(f"{row[1]} {row[2]}", "%m/%d/%Y %H:%M:%S")
            value = float(row[channel_offset + tag_index])
        except (ValueError, IndexError):
            continue
        readings.setdefault(timestamp, value)
    return readings


def delta(readings: dict[datetime, dict[str, str]], timestamp: datetime, tag: str) -> float | None:
    previous = timestamp - timedelta(minutes=15)
    if timestamp not in readings or previous not in readings:
        return None
    current_value = parse_number(readings[timestamp].get(tag))
    previous_value = parse_number(readings[previous].get(tag))
    if current_value is None or previous_value is None:
        return None
    return current_value - previous_value


def delta_smec(readings: dict[datetime, float], timestamp: datetime, rollover: float = 599999.9994) -> float | None:
    previous = timestamp - timedelta(minutes=15)
    if timestamp not in readings or previous not in readings:
        return None
    value = readings[timestamp] - readings[previous]
    if value < 0:
        return (rollover - readings[previous]) + readings[timestamp]
    return value


def zero_if_none(value: float | None) -> float:
    return 0.0 if value is None else value


def build_pando(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float]) -> list[dict[str, object]]:
    rows = []
    start = datetime(2026, 1, 1, 0, 0)
    for index in range(31 * 96):
        timestamp = start + timedelta(minutes=15 * index)
        bruta_u1 = delta(balance, timestamp, "G1_JQ_GEN_P_EXP")
        bruta_u2 = delta(balance, timestamp, "G2_JQ_GEN_P_EXP")
        consumo_u1 = delta(balance, timestamp, "G1_JQ_UAB_P_EXP")
        consumo_u2 = delta(balance, timestamp, "G2_JQ_UAB_P_EXP")
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
        rows.append(
            {
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
            }
        )
    return rows


def build_ml(balance: dict[datetime, dict[str, str]], smec: dict[datetime, float]) -> list[dict[str, object]]:
    rows = []
    start = datetime(2026, 1, 1, 0, 0)
    for index in range(31 * 96):
        timestamp = start + timedelta(minutes=15 * index)
        brutas = [delta(balance, timestamp, f"G{i}_JQ_GEN_P_EXP") for i in (1, 2, 3)]
        netas = [delta(balance, timestamp, f"G{i}_JQ_LIN_P_EXP") for i in (1, 2, 3)]
        consumos = [delta(balance, timestamp, f"G{i}_JQ_UAB_P_EXP") for i in (1, 2, 3)]
        se = delta_smec(smec, timestamp)
        bruta_total = None if any(value is None for value in brutas) else sum(brutas)  # type: ignore[arg-type]
        neta_total = None if any(value is None for value in netas) else sum(netas)  # type: ignore[arg-type]
        consumo_total = None if any(value is None for value in consumos) else sum(consumos)  # type: ignore[arg-type]
        perdida_interna = None if None in (bruta_total, neta_total, consumo_total) else bruta_total - neta_total - consumo_total
        perdida_linea = None if None in (neta_total, se) else neta_total - se
        perdida_total = None if None in (perdida_interna, perdida_linea) else perdida_interna + perdida_linea
        rows.append(
            {
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
            }
        )
    return rows


def summarize_daily(rows: list[dict[str, object]], columns: list[str]) -> list[dict[str, object]]:
    by_day: dict[datetime, dict[str, object]] = defaultdict(dict)
    for row in rows:
        timestamp = datetime(1899, 12, 30) + timedelta(days=float(row["Timestamp"]))
        day = timestamp.date()
        item = by_day.setdefault(day, {"Fecha": excel_serial(datetime(day.year, day.month, day.day))})
        for column in columns:
            value = row.get(column)
            if isinstance(value, (int, float)):
                item[column] = float(item.get(column, 0.0)) + float(value)
        item["Intervalos no medidos"] = int(item.get("Intervalos no medidos", 0)) + (1 if row.get("Calidad") != "medido" else 0)
    return [by_day[key] for key in sorted(by_day)]


def summarize_kpis(rows: list[dict[str, object]], plant: str, total_columns: list[str]) -> list[dict[str, object]]:
    totals = {}
    for column in total_columns:
        totals[column] = sum(float(row[column]) for row in rows if isinstance(row.get(column), (int, float)))
    labels = [{"KPI": column, "Valor": value} for column, value in totals.items()]
    labels.append({"KPI": "Intervalos no medidos", "Valor": sum(1 for row in rows if row.get("Calidad") != "medido")})
    if plant == "PDO":
        labels.append({"KPI": "Supuesto ratio línea Pando", "Valor": RATIO_LINEA_PANDO})
        labels.append({"KPI": "Nota", "Valor": "Pando usa SMEC Primavera (MWH3O). La primera fila 00:00 queda como hueco si falta lectura SCADA anterior."})
    else:
        labels.append({"KPI": "Nota", "Valor": "Montelirio usa SMEC El Alto (MWH3O). La primera fila 00:00 queda como hueco si falta lectura SCADA anterior."})
    return labels


def xlsx_col(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def xlsx_cell(value: object, row: int, col: int) -> str:
    ref = f"{xlsx_col(col)}{row}"
    if value is None or value == "":
        return f'<c r="{ref}"/>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def xlsx_sheet(title: str, subtitle: str, rows: list[dict[str, object]], columns: list[str]) -> str:
    xml_rows = [
        f'<row r="1">{xlsx_cell("Operaciones EISA", 1, 1)}</row>',
        f'<row r="2">{xlsx_cell(subtitle, 2, 1)}</row>',
        '<row r="3">' + "".join(xlsx_cell(column, 3, idx) for idx, column in enumerate(columns, start=1)) + '</row>',
    ]
    for row_idx, row in enumerate(rows, start=4):
        xml_rows.append(
            f'<row r="{row_idx}">'
            + "".join(xlsx_cell(row.get(column), row_idx, col_idx) for col_idx, column in enumerate(columns, start=1))
            + "</row>"
        )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheetData>{''.join(xml_rows)}</sheetData>
</worksheet>'''


def write_xlsx(path: Path, sheets: list[tuple[str, str, list[dict[str, object]], list[str]]]) -> None:
    content = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for idx in range(1, len(sheets) + 1):
        content.append(f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content.append('</Types>')
    workbook_sheets = []
    workbook_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for idx, (name, _subtitle, _rows, _columns) in enumerate(sheets, start=1):
        workbook_sheets.append(f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
        workbook_rels.append(f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>')
    workbook_rels.append(f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{''.join(workbook_sheets)}</sheets></workbook>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs></styleSheet>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
        archive.writestr("xl/styles.xml", styles)
        for idx, (_name, subtitle, rows, columns) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", xlsx_sheet(_name, subtitle, rows, columns))


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="energia_15min_enero_"))
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir()
    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            archive.extractall(temp_dir)
        pdo_balance = read_balance(next(temp_dir.rglob("Balance de Energía/Balance de nergía PND enero 2026.xlsx")), "PDO")
        ml_balance = read_balance(next(temp_dir.rglob("Balance de Energía/Balance Energia ML Enero 2026.xlsx")), "ML")
        primavera = read_smec(next(temp_dir.rglob("SMEC/SMEC Enero Primavera 2026.csv")))
        el_alto = read_smec(next(temp_dir.rglob("SMEC/SMEC Enero El Alto 2026 .csv")))

        pando_rows = build_pando(pdo_balance, primavera)
        ml_rows = build_ml(ml_balance, el_alto)

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

        write_csv(OUT_DIR / "Pando_Consolidado_15min_Enero_2026.csv", pando_rows, pando_columns)
        write_csv(OUT_DIR / "Montelirio_Consolidado_15min_Enero_2026.csv", ml_rows, ml_columns)
        write_xlsx(
            OUT_DIR / "Operaciones_EISA_Energia_Pando_Enero_2026_15min.xlsx",
            [
                ("Diario", "Reporte de Energía • Pando • Enero 2026", pando_daily, ["Fecha"] + pando_columns[1:-1] + ["Intervalos no medidos"]),
                ("Resumen", "Resumen • Pando • Enero 2026", pando_kpis, ["KPI", "Valor"]),
                ("Consolidado", "Consolidado 15-min • Pando • Enero 2026", pando_rows, pando_columns),
            ],
        )
        write_xlsx(
            OUT_DIR / "Operaciones_EISA_Energia_Montelirio_Enero_2026_15min.xlsx",
            [
                ("Diario", "Reporte de Energía • Montelirio • Enero 2026", ml_daily, ["Fecha"] + ml_columns[1:-1] + ["Intervalos no medidos"]),
                ("Resumen", "Resumen • Montelirio • Enero 2026", ml_kpis, ["KPI", "Valor"]),
                ("Consolidado", "Consolidado 15-min • Montelirio • Enero 2026", ml_rows, ml_columns),
            ],
        )
        print(OUT_DIR)
        print("Pando", pando_kpis[:7])
        print("Montelirio", ml_kpis[:7])
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
