from __future__ import annotations

import argparse
import csv
import socket
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue


OD_COLUMNS = [
    "HON",
    "HOL",
    "RSH",
    "HMP",
    "HMHP",
    "FOH",
    "SYNC_HR",
    "PMP_HR",
    "EFDH",
    "EFDHRS",
    "EFDHSH",
    "SAL",
    "MWEFECTIVO",
    "MWDISP",
    "TOTAL_PERIODO",
]


def prop(name: str, value: object) -> PropertyValue:
    item = PropertyValue()
    item.Name = name
    item.Value = value
    return item


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_office(port: int) -> subprocess.Popen[bytes]:
    profile = Path(tempfile.mkdtemp(prefix="lo_profile_maestro_od_"))
    profile.mkdir(exist_ok=True)
    return subprocess.Popen(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation=file://{profile}",
            f"--accept=socket,host=localhost,port={port};urp;StarOffice.ComponentContext",
            "--norestore",
            "--nodefault",
            "--nofirststartwizard",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def connect_office(port: int, retries: int = 40) -> object:
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local_ctx)
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            ctx = resolver.resolve(f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext")
            return ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError("No se pudo conectar a LibreOffice headless") from last_error


def cell_value(sheet: object, col: int, row: int) -> object:
    cell = sheet.getCellByPosition(col, row)
    return cell.Value if cell.Value != 0 else cell.String


def clean(value: object) -> str:
    return str(value or "").strip()


def as_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = clean(value).replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_date(value: object) -> date | None:
    if isinstance(value, (int, float)) and value:
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(value))
    text = clean(value)
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def classify_unit(raw_unit: str, path: Path) -> tuple[str, str]:
    unit = (raw_unit or path.parent.name).upper().replace("MLIG", "MLG").replace("MIRG", "MLG")
    if unit.startswith("MLG"):
        return "ML", unit.replace("MLG", "MLG")
    if unit.startswith("PDOG"):
        return "PDO", unit
    if unit.startswith("ECSG"):
        return "ECO1", unit
    for eco in range(2, 6):
        if unit.startswith(f"ECS{eco}G"):
            return f"ECO{eco}", unit
    return "SIN_ASIGNAR", unit


def find_total_row(sheet: object) -> int | None:
    for row in range(0, 100):
        if clean(sheet.getCellByPosition(0, row).String).lower() == "total":
            return row
    return None


def load_file(desktop: object, path: Path) -> list[dict[str, object]]:
    url = uno.systemPathToFileUrl(str(path))
    doc = desktop.loadComponentFromURL(url, "_blank", 0, (prop("Hidden", True), prop("ReadOnly", True)))
    rows: list[dict[str, object]] = []
    try:
        sheets = doc.getSheets()
        for sheet_name in sheets.getElementNames():
            if not str(sheet_name).isdigit():
                continue
            sheet = sheets.getByName(sheet_name)
            op_date = parse_date(cell_value(sheet, 1, 3))
            if op_date is None:
                continue
            raw_unit = clean(cell_value(sheet, 1, 2))
            plant, unit = classify_unit(raw_unit, path)
            total_row = find_total_row(sheet)
            if total_row is None:
                continue
            for hour_row in range(5, total_row):
                values = [as_float(cell_value(sheet, col, hour_row)) for col in range(1, 16)]
                if len(values) < 15:
                    continue
                hour_index = hour_row - 5
                if hour_index < 0 or hour_index > 23:
                    continue
                record = {
                    "planta_id": plant,
                    "unidad_id": unit,
                    "fecha": op_date.isoformat(),
                    "hora_inicio": f"{hour_index:02d}:00",
                    "hora_fin": "24:00" if hour_index == 23 else f"{hour_index + 1:02d}:00",
                    "timestamp_inicio": datetime.combine(op_date, datetime.min.time()).replace(hour=hour_index).isoformat(sep=" "),
                    "timestamp_fin": (datetime.combine(op_date, datetime.min.time()) + timedelta(hours=hour_index + 1)).isoformat(sep=" "),
                    "archivo_origen": str(path),
                    "hoja_origen": sheet_name,
                    "fila_origen": hour_row + 1,
                }
                for column, value in zip(OD_COLUMNS, values):
                    record[column.lower()] = value
                hon, hol, rsh, hmp, hmhp, foh, sync_hr, pmp_hr = values[:8]
                record["en_linea"] = 1 if (hon + hol) > 0.0001 else 0
                record["disponible"] = 1 if (hon + hol + rsh + sync_hr + pmp_hr) > 0.0001 else 0
                record["fuera_forzada"] = 1 if foh > 0.0001 else 0
                record["limitada"] = 1 if (hol + rsh) > 0.0001 else 0
                rows.append(record)
    finally:
        try:
            doc.close(True)
        except Exception:
            try:
                doc.dispose()
            except Exception:
                pass
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "planta_id",
        "unidad_id",
        "fecha",
        "hora_inicio",
        "hora_fin",
        "timestamp_inicio",
        "timestamp_fin",
        "en_linea",
        "disponible",
        "fuera_forzada",
        "limitada",
        *[column.lower() for column in OD_COLUMNS],
        "archivo_origen",
        "hoja_origen",
        "fila_origen",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea registro maestro horario desde Operacion Diaria.")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("maestro_operacion_diaria"))
    args = parser.parse_args()

    temp_dir = Path(tempfile.mkdtemp(prefix="maestro_od_"))
    args.out_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(args.zip) as archive:
            archive.extractall(temp_dir)
        files = sorted(path for path in temp_dir.rglob("OD_DD*.xls*") if path.is_file())
        office_port = free_port()
        process = start_office(office_port)
        desktop = connect_office(office_port)
        try:
            rows: list[dict[str, object]] = []
            for idx, path in enumerate(files, start=1):
                loaded = load_file(desktop, path)
                rows.extend(loaded)
                print(f"{idx}/{len(files)} {path.name} filas={len(loaded)}", flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        csv_path = args.out_dir / f"maestro_operacion_diaria_{args.zip.stem.replace(' ', '_').lower()}.csv"
        write_csv(csv_path, rows)
        summary: dict[tuple[str, str], dict[str, float]] = {}
        for row in rows:
            key = (str(row["planta_id"]), str(row["unidad_id"]))
            item = summary.setdefault(key, {"horas": 0, "en_linea": 0, "foh": 0})
            item["horas"] += 1
            item["en_linea"] += int(row["en_linea"])
            item["foh"] += float(row["foh"])
        summary_path = args.out_dir / f"resumen_maestro_operacion_diaria_{args.zip.stem.replace(' ', '_').lower()}.csv"
        with summary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["planta_id", "unidad_id", "horas", "horas_en_linea", "foh"])
            writer.writeheader()
            for (plant, unit), values in sorted(summary.items()):
                writer.writerow({
                    "planta_id": plant,
                    "unidad_id": unit,
                    "horas": values["horas"],
                    "horas_en_linea": values["en_linea"],
                    "foh": values["foh"],
                })
        print(csv_path)
        print(summary_path)
        print(f"filas={len(rows)} unidades={len(summary)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
