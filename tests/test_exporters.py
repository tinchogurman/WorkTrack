"""Acceptance 9: export a report to Excel and verify its contents (also CSV)."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook

from worktrack.analytics.periods import Period
from worktrack.services.entry_service import EntryDraft
from worktrack.services.exporters import ExportError, default_filename, export_csv, export_xlsx

from conftest import BA

H = 3600


def at(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=BA)


@pytest.fixture
def report(services, project, other_project, clock):
    clock.set(datetime(2026, 3, 20, 18, 0, tzinfo=BA))
    add = lambda p, t, s, e, d=None: services.entries.add_manual(EntryDraft(p.id, t, s, e, d))  # noqa: E731
    add(project, "ETL", at(2, 9), at(2, 10, 30), "carga; con punto y coma")
    add(other_project, "API", at(3, 14), at(3, 15))
    add(project, "ETL", at(15, 23), at(16, 1))  # crosses midnight
    return services.reports.build(Period.custom(date(2026, 3, 1), date(2026, 3, 15)))


def test_report_totals(report):
    # 1.5 h + 1 h + only 1 h of the midnight session (16th is outside the range)
    assert report.total_seconds == int(3.5 * H)
    assert report.sessions == 3
    assert [d.in_period_seconds for d in report.details] == [5400, 3600, 3600]
    assert [d.duration_seconds for d in report.details] == [5400, 3600, 7200]


def test_xlsx_contents(report, tmp_path):
    path = export_xlsx(report, tmp_path / "exports" / default_filename(report, "xlsx"))
    assert path.name == "WorkTrack_2026-03-01_2026-03-15.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["Resumen", "Por proyecto", "Por tarea", "Por día", "Por semana", "Sesiones"]

    summary = {row[0].value: row[1] for row in wb["Resumen"].iter_rows()}
    assert summary["Total (horas)"].value == 3.5
    # stored as an Excel time (fraction of a day); openpyxl reads it back as timedelta
    assert summary["Total (HH:MM:SS)"].value == timedelta(hours=3, minutes=30)
    assert summary["Total (HH:MM:SS)"].number_format == "[h]:mm:ss"
    assert summary["Sesiones"].value == 3
    assert summary["Días con actividad"].value == 3

    projects = list(wb["Por proyecto"].iter_rows(min_row=2, values_only=True))
    assert projects[0][0] == "Data Engineering" and projects[0][2] == 2.5
    assert projects[1][0] == "Desarrollo Python" and projects[1][2] == 1.0
    assert projects[-1][0] == "Total" and projects[-1][2] == 3.5

    days = list(wb["Por día"].iter_rows(min_row=2, values_only=True))
    assert len(days) == 15 + 1  # every day of the range + total row
    by_date = {r[0].date(): r[3] for r in days[:-1]}
    assert by_date[date(2026, 3, 2)] == 1.5 and by_date[date(2026, 3, 15)] == 1.0
    assert sum(by_date.values()) == pytest.approx(3.5)

    weeks = list(wb["Por semana"].iter_rows(min_row=2, values_only=True))
    assert weeks[-1][4] == 3.5
    assert weeks[0][1].date() == date(2026, 3, 1)  # clipped to the range start

    sessions = list(wb["Sesiones"].iter_rows(min_row=2, values_only=True))
    crossing = sessions[2]
    assert crossing[3] == datetime(2026, 3, 15, 23, 0) and crossing[4] == datetime(2026, 3, 16, 1, 0)
    assert crossing[6] == 2.0 and crossing[8] == 1.0
    assert crossing[5] == timedelta(hours=2) and crossing[7] == timedelta(hours=1)
    assert sessions[-1][0] == "Total" and sessions[-1][6] == 4.5 and sessions[-1][8] == 3.5
    assert wb["Sesiones"]["F2"].number_format == "[h]:mm:ss"


def test_csv_contents(report, tmp_path):
    path = export_csv(report, tmp_path / default_filename(report, "csv"))
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    assert rows[0][0] == "Fecha" and rows[0][6] == "Horas"
    assert rows[1] == [
        "02/03/2026", "Data Engineering", "ETL", "02/03/2026 09:00:00", "02/03/2026 10:30:00",
        "01:30:00", "1,50", "01:30:00", "1,50", "carga; con punto y coma",
    ]
    assert rows[3][6] == "2,00" and rows[3][8] == "1,00"
    assert len(rows) == 4


def test_empty_report_exports(services, tmp_path):
    r = services.reports.build(Period.day(date(2026, 1, 1)))
    wb = load_workbook(export_xlsx(r, tmp_path / "empty.xlsx"))
    assert {row[0].value: row[1].value for row in wb["Resumen"].iter_rows()}["Sesiones"] == 0
    assert len(export_csv(r, tmp_path / "empty.csv").read_text(encoding="utf-8-sig").splitlines()) == 1


def test_export_error_is_clear(report, tmp_path):
    target = tmp_path / "is_a_directory.xlsx"
    target.mkdir()
    with pytest.raises(ExportError) as info:
        export_xlsx(report, target)
    assert "No se pudo guardar" in info.value.message
