"""Export a Report to Excel (.xlsx, one sheet per section) or CSV (session detail).

Excel: durations are real Excel times ([h]:mm:ss) and decimal hours are
numbers, so both can be summed in the spreadsheet. CSV: ';' separator,
decimal comma and UTF-8 with BOM so it opens directly in Spanish Excel.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from worktrack.analytics.periods import fmt_date
from worktrack.core.errors import WorkTrackError
from worktrack.core.timeutils import decimal_hours, format_decimal_hours, format_hms
from worktrack.services.report_service import Report

log = logging.getLogger(__name__)

WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DURATION_FMT = "[h]:mm:ss"
HOURS_FMT = "0.00"
PERCENT_FMT = "0%"
DATE_FMT = "dd/mm/yyyy"
DATETIME_FMT = "dd/mm/yyyy hh:mm:ss"
HEADER_FILL = PatternFill("solid", fgColor="2D323D")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TOTAL_FONT = Font(bold=True)

CSV_COLUMNS = [
    "Fecha", "Proyecto", "Tarea", "Inicio", "Fin",
    "Duración (HH:MM:SS)", "Horas", "En el período (HH:MM:SS)", "Horas en el período", "Descripción",
]


class ExportError(WorkTrackError):
    pass


def default_filename(report: Report, extension: str) -> str:
    p = report.period
    return f"WorkTrack_{p.start:%Y-%m-%d}_{p.end:%Y-%m-%d}.{extension}"


def _excel_duration(seconds: int) -> float:
    return seconds / 86400


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)  # Excel has no time zones; values are already local


def _write_table(ws, headers: list[str], rows: list[list], formats: dict[int, str], total: list | None = None) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append(row)
    if total is not None:
        ws.append(total)
        for cell in ws[ws.max_row]:
            cell.font = TOTAL_FONT
    for col, fmt in formats.items():
        for (cell,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            cell.number_format = fmt
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    for i, header in enumerate(headers, start=1):
        values = [header] + [r[i - 1] for r in rows]
        width = max(len(str(v)) if not isinstance(v, (int, float, datetime)) else 12 for v in values)
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)


def _save(path: Path, writer) -> Path:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        writer(path)
    except PermissionError as exc:
        log.warning("Export failed (permission): %s", exc)
        raise ExportError(
            f"No se pudo guardar «{path.name}». Si el archivo está abierto en Excel, cerralo e intentá de nuevo."
        ) from exc
    except OSError as exc:
        log.warning("Export failed: %s", exc)
        raise ExportError(f"No se pudo guardar el archivo en «{path.parent}».") from exc
    log.info("Report exported to %s", path)
    return path


def export_xlsx(report: Report, path: Path | str) -> Path:
    wb = Workbook()

    ws = wb.active
    ws.title = "Resumen"
    p = report.period
    summary = [
        ("Reporte", report.title),
        ("Período", f"{fmt_date(p.start)} – {fmt_date(p.end)}"),
        ("Proyecto", report.project_filter),
        ("Tarea", report.task_filter),
        ("Generado", _naive(report.generated_at)),
        ("Total (HH:MM:SS)", _excel_duration(report.total_seconds)),
        ("Total (horas)", decimal_hours(report.total_seconds)),
        ("Sesiones", report.sessions),
        ("Días con actividad", report.days_active),
        ("Nota", "Solo sesiones finalizadas. Los totales reparten entre días las sesiones que "
                 "cruzan la medianoche; la hoja Sesiones muestra cada sesión completa."),
    ]
    for label, value in summary:
        ws.append([label, value])
        ws.cell(ws.max_row, 1).font = TOTAL_FONT
    ws["B5"].number_format = DATETIME_FMT
    ws["B6"].number_format = DURATION_FMT
    ws["B7"].number_format = HOURS_FMT
    ws["A1"].font = Font(bold=True, size=13)
    ws["B1"].font = Font(bold=True, size=13)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60
    ws["B10"].alignment = Alignment(wrap_text=True, vertical="top")

    total_row_tail = [_excel_duration(report.total_seconds), decimal_hours(report.total_seconds)]

    ws = wb.create_sheet("Por proyecto")
    rows = [
        [r.project, _excel_duration(r.seconds), decimal_hours(r.seconds), float(r.share)]
        for r in report.per_project.itertuples()
    ]
    _write_table(ws, ["Proyecto", "Duración", "Horas", "%"], rows,
                 {2: DURATION_FMT, 3: HOURS_FMT, 4: PERCENT_FMT}, ["Total", *total_row_tail, 1 if rows else 0])

    ws = wb.create_sheet("Por tarea")
    rows = [
        [r.project, r.task, _excel_duration(r.seconds), decimal_hours(r.seconds), float(r.share)]
        for r in report.per_task.itertuples()
    ]
    _write_table(ws, ["Proyecto", "Tarea", "Duración", "Horas", "%"], rows,
                 {3: DURATION_FMT, 4: HOURS_FMT, 5: PERCENT_FMT}, ["Total", "", *total_row_tail, 1 if rows else 0])

    ws = wb.create_sheet("Por día")
    rows = [
        [r.date, WEEKDAYS_ES[r.date.weekday()], _excel_duration(r.seconds), decimal_hours(r.seconds)]
        for r in report.per_day.itertuples()
    ]
    _write_table(ws, ["Fecha", "Día", "Duración", "Horas"], rows,
                 {1: DATE_FMT, 3: DURATION_FMT, 4: HOURS_FMT}, ["Total", "", *total_row_tail])

    ws = wb.create_sheet("Por semana")
    rows = []
    for r in report.per_week.itertuples():
        start = max(r.week, p.start)
        end = min(r.week + timedelta(days=6), p.end)
        rows.append([r.label.split(" (")[0], start, end, _excel_duration(r.seconds), decimal_hours(r.seconds)])
    _write_table(ws, ["Semana", "Desde", "Hasta", "Duración", "Horas"], rows,
                 {2: DATE_FMT, 3: DATE_FMT, 4: DURATION_FMT, 5: HOURS_FMT}, ["Total", "", "", *total_row_tail])

    ws = wb.create_sheet("Sesiones")
    rows = [
        [
            d.start.date(), d.project, d.task, _naive(d.start), _naive(d.end),
            _excel_duration(d.duration_seconds), decimal_hours(d.duration_seconds),
            _excel_duration(d.in_period_seconds), decimal_hours(d.in_period_seconds),
            d.description,
        ]
        for d in report.details
    ]
    full_total = sum(d.duration_seconds for d in report.details)
    _write_table(
        ws,
        ["Fecha", "Proyecto", "Tarea", "Inicio", "Fin", "Duración", "Horas",
         "En el período", "Horas en el período", "Descripción"],
        rows,
        {1: DATE_FMT, 4: DATETIME_FMT, 5: DATETIME_FMT, 6: DURATION_FMT, 7: HOURS_FMT,
         8: DURATION_FMT, 9: HOURS_FMT},
        ["Total", "", "", "", "", _excel_duration(full_total), decimal_hours(full_total), *total_row_tail, ""],
    )
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 20

    return _save(Path(path), wb.save)


def export_csv(report: Report, path: Path | str) -> Path:
    def write(target: Path) -> None:
        with open(target, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(CSV_COLUMNS)
            for d in report.details:
                writer.writerow([
                    d.start.strftime("%d/%m/%Y"),
                    d.project,
                    d.task,
                    d.start.strftime("%d/%m/%Y %H:%M:%S"),
                    d.end.strftime("%d/%m/%Y %H:%M:%S"),
                    format_hms(d.duration_seconds),
                    format_decimal_hours(d.duration_seconds),
                    format_hms(d.in_period_seconds),
                    format_decimal_hours(d.in_period_seconds),
                    d.description,
                ])

    return _save(Path(path), write)
