"""UI tests (headless, pytest-qt). Business rules are covered by service tests;
these check that the widgets are wired to them correctly."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from worktrack.services.context import AppServices
from worktrack.ui.dialogs.entry_dialog import EntryDialog
from worktrack.ui.dialogs.recovery_dialog import RecoveryDialog
from worktrack.ui.errors import GENERIC, user_message
from worktrack.ui.main_window import SECTIONS, MainWindow
from worktrack.ui.widgets import utc_to_qdatetime


@pytest.fixture(autouse=True)
def no_modal_boxes(monkeypatch):
    """Record message boxes instead of blocking the test run."""
    shown = []

    def fake(kind):
        def _box(parent, title, text, *args, **kwargs):
            shown.append((kind, text))
            return QMessageBox.Ok
        return _box

    for kind in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(fake(kind)))

    def fake_exec(box):
        # custom boxes (confirmations, exit prompt): behave as "Cancel"
        shown.append(("exec", box.text()))
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return shown


@pytest.fixture
def window(qtbot, services):
    w = MainWindow(services)
    qtbot.addWidget(w)
    w.show()
    yield w
    w.shutdown()  # stop timers before the database is closed


def test_main_window_sections(window):
    assert window.nav.count() == len(SECTIONS) == 6
    names = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert names == ["Timer", "Dashboard", "Projects", "History", "Reports", "Settings"]
    assert not (window.nav.item(5).flags() & Qt.ItemIsEnabled)  # Settings: phase 3
    window.go_to(3)
    assert window.stack.currentWidget() is window.history_view
    window.go_to(5)  # disabled: ignored
    assert window.stack.currentWidget() is window.history_view
    window.go_to(1)
    assert window.stack.currentWidget() is window.dashboard_view


def test_dashboard_view_matches_records(window, services, project, other_project, clock):
    from worktrack.services.entry_service import EntryDraft

    now = clock.now()
    services.entries.add_manual(EntryDraft(project.id, "A", now - timedelta(hours=3), now - timedelta(hours=1, minutes=30)))
    services.entries.add_manual(EntryDraft(other_project.id, "B", now - timedelta(hours=1), now))
    window.signals.entries_changed.emit()
    window.go_to(1)
    dv = window.dashboard_view
    assert dv.data is not None
    assert dv.kpi_total.value.text() == "02:30:00"
    assert dv.kpi_today.value.text() == "02:30:00"
    assert dv.kpi_sessions.value.text() == "2"
    assert dv.kpi_top.value.text() == project.name
    assert "2,50 h" in dv.kpi_total.detail.text()
    assert dv.chart_project._values == pytest.approx([1.5, 1.0])
    dv.period_picker.set_preset("week")
    assert dv.data.period.days == 7


def test_reports_view_generate_and_export(window, services, project, other_project, clock, tmp_path, monkeypatch, no_modal_boxes):
    from openpyxl import load_workbook
    from PySide6.QtWidgets import QFileDialog

    from worktrack.services.entry_service import EntryDraft

    now = clock.now()
    services.entries.add_manual(EntryDraft(project.id, "A", now - timedelta(hours=3), now - timedelta(hours=1, minutes=30)))
    services.entries.add_manual(EntryDraft(other_project.id, "B", now - timedelta(hours=1), now))
    window.signals.projects_changed.emit()  # projects were created after the window
    window.signals.entries_changed.emit()
    window.go_to(4)
    rv = window.reports_view
    assert rv.report is not None and rv.report.total_seconds == 9000
    assert rv.kpi_total.value.text() == "02:30:00"
    assert rv.table_project.rowCount() == 2 and rv.table_sessions.rowCount() == 2
    assert rv.export_xlsx_btn.isEnabled()

    rv.kind.setCurrentIndex(rv.kind.findData("day"))
    assert rv.report.period.days == 1

    rv.filter.project_combo.setCurrentIndex(rv.filter.project_combo.findData(other_project.id))
    assert rv.report.total_seconds == 3600 and rv.report.project_filter == other_project.name

    target = tmp_path / "out" / "reporte"  # no extension: it is added
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    rv.export("xlsx")
    wb = load_workbook(tmp_path / "out" / "reporte.xlsx")
    summary = {row[0].value: row[1].value for row in wb["Resumen"].iter_rows()}
    assert summary["Total (horas)"] == 1.0 and summary["Proyecto"] == other_project.name
    rv.export("csv")
    assert (tmp_path / "out" / "reporte.csv").exists()
    assert any("exportado" in text for _, text in no_modal_boxes)


def test_reports_invalid_range(window):
    window.go_to(4)
    rv = window.reports_view
    rv.kind.setCurrentIndex(rv.kind.findData("range"))
    rv.to_date.setDate(rv.from_date.date().addDays(-1))
    assert "anterior" in rv.error.text()


def test_dashboard_empty(window):
    window.go_to(1)
    assert window.dashboard_view.kpi_total.value.text() == "00:00:00"
    assert window.dashboard_view.chart_day._values == []


def test_play_stop_from_ui(qtbot, window, services, project, clock):
    window.signals.projects_changed.emit()
    tv = window.timer_view
    assert tv.project_combo.current_project_id() == project.id
    tv.task_combo.setEditText("ETL nightly")
    tv.description_edit.setText("carga")
    qtbot.mouseClick(tv.play_button, Qt.LeftButton)
    assert tv.is_running()
    assert not tv.play_button.isEnabled() and tv.stop_button.isEnabled()
    assert not tv.project_combo.isEnabled()

    clock.advance(seconds=65)
    tv._update_display()
    assert tv.display.text() == "00:01:05"
    assert "00:01:05" in window.windowTitle()

    qtbot.mouseClick(tv.stop_button, Qt.LeftButton)
    assert not tv.is_running()
    entry = services.entries.list_entries()[0].entry
    assert entry.duration_seconds == 65 and entry.description == "carga"
    assert tv.today_table.rowCount() == 1
    assert window.history_view.model.rowCount() == 1


def test_toggle_shortcut_logic(window, project, clock):
    window.signals.projects_changed.emit()
    tv = window.timer_view
    tv.task_combo.setEditText("X")
    tv.toggle()
    assert tv.is_running()
    clock.advance(seconds=3)
    tv.toggle()
    assert not tv.is_running()


def test_play_without_task_does_nothing(window, project, no_modal_boxes):
    window.signals.projects_changed.emit()
    window.timer_view.task_combo.setEditText("")
    window.timer_view.start()
    assert not window.timer_view.is_running()
    assert no_modal_boxes and no_modal_boxes[0][0] == "information"


def test_timer_shows_session_already_active_in_db(qtbot, services, project, clock):
    services.timer.start(project.id, "Desde otro lado")
    clock.advance(minutes=2)
    w = MainWindow(services)
    qtbot.addWidget(w)
    assert w.timer_view.is_running()
    assert w.timer_view.task_combo.currentText() == "Desde otro lado"
    assert w.timer_view.display.text() == "00:02:00"
    w.shutdown()


def test_entry_dialog_shows_duration_before_saving(qtbot, services, project, clock):
    dialog = EntryDialog(services)
    qtbot.addWidget(dialog)
    now = clock.now()
    dialog.task_combo.setEditText("Manual")
    dialog.start_edit.setDateTime(utc_to_qdatetime(now - timedelta(hours=2)))
    dialog.end_edit.setDateTime(utc_to_qdatetime(now - timedelta(minutes=30)))
    assert "01:30:00" in dialog.duration_label.text()
    assert "1,50 h" in dialog.duration_label.text()
    assert dialog.save_button.isEnabled()
    dialog._save()
    assert dialog.saved is not None and dialog.saved.duration_seconds == 5400


def test_entry_dialog_blocks_invalid_and_overlap(qtbot, services, project, clock):
    now = clock.now()
    services.timer.start(project.id, "En curso")
    clock.advance(hours=1)
    dialog = EntryDialog(services)
    qtbot.addWidget(dialog)
    dialog.task_combo.setEditText("Manual")
    dialog.start_edit.setDateTime(utc_to_qdatetime(now + timedelta(minutes=10)))
    dialog.end_edit.setDateTime(utc_to_qdatetime(now + timedelta(minutes=20)))
    assert "superpone" in dialog.duration_label.text()
    assert not dialog.save_button.isEnabled()
    dialog.end_edit.setDateTime(utc_to_qdatetime(now + timedelta(minutes=5)))
    assert "posterior" in dialog.duration_label.text()
    assert not dialog.save_button.isEnabled()


def test_entry_dialog_edit_recalculates(qtbot, services, project, clock):
    from worktrack.services.entry_service import EntryDraft

    now = clock.now()
    entry = services.entries.add_manual(EntryDraft(project.id, "T", now - timedelta(hours=3), now - timedelta(hours=2)))
    dialog = EntryDialog(services, services.entries.get_view(entry.id))
    qtbot.addWidget(dialog)
    assert "01:00:00" in dialog.duration_label.text()
    dialog.end_edit.setDateTime(utc_to_qdatetime(now - timedelta(minutes=90)))
    assert "01:30:00" in dialog.duration_label.text()
    dialog._save()
    assert services.entries.get_view(entry.id).entry.duration_seconds == 5400


def test_history_blocks_editing_active_session(window, services, project, no_modal_boxes):
    services.timer.start(project.id, "ETL")
    window.history_view.refresh()
    window.history_view.table.selectRow(0)
    window.history_view.delete_entry()
    assert services.timer.get_active() is not None
    assert any("en curso" in text for _, text in no_modal_boxes)


def test_history_filters(window, services, project, other_project, clock):
    from worktrack.services.entry_service import EntryDraft

    now = clock.now()
    services.entries.add_manual(EntryDraft(project.id, "A", now - timedelta(hours=3), now - timedelta(hours=2)))
    services.entries.add_manual(EntryDraft(other_project.id, "B", now - timedelta(hours=2), now - timedelta(hours=1)))
    services.entries.add_manual(EntryDraft(project.id, "Old", now - timedelta(days=90), now - timedelta(days=90) + timedelta(hours=1)))
    window.signals.projects_changed.emit()
    hv = window.history_view
    assert hv.period_picker.preset_key() == "last30"
    assert hv.model.rowCount() == 2
    hv.period_picker.set_preset("all")
    assert hv.model.rowCount() == 3
    hv.project_filter.project_combo.setCurrentIndex(hv.project_filter.project_combo.findData(project.id))
    assert hv.model.rowCount() == 2
    hv.project_filter.task_combo.setCurrentIndex(hv.project_filter.task_combo.findText("Old"))
    assert hv.model.rowCount() == 1
    hv.clear_filters()
    assert hv.model.rowCount() == 3
    assert "3 sesiones" in hv.summary.text()


def test_history_custom_range_validation(window):
    hv = window.history_view
    hv.period_picker.set_preset("custom")
    hv.period_picker.to_edit.setDate(hv.period_picker.from_edit.date().addDays(-1))
    assert hv.filter_error.isVisible() or "anterior" in hv.filter_error.text()


def test_recovery_dialog_finish_at_last_seen(qtbot, services, project, db_file, clock):
    services.timer.start(project.id, "ETL")
    clock.advance(minutes=10)
    services.timer.heartbeat()
    services.conn.close()
    clock.advance(hours=2)
    reopened = AppServices.open(db_file, clock)
    try:
        info = reopened.recovery.check()
        dialog = RecoveryDialog(reopened.recovery, info)
        qtbot.addWidget(dialog)
        assert dialog.opt_last.isChecked()  # safest default
        dialog._apply()
        assert dialog.choice == "finish_last_seen"
        assert reopened.entries.list_entries()[0].entry.duration_seconds == 600
    finally:
        reopened.close()


def test_recovery_dialog_dismiss_keeps_session(qtbot, services, project, clock):
    services.timer.start(project.id, "ETL")
    dialog = RecoveryDialog(services.recovery, services.recovery.check())
    qtbot.addWidget(dialog)
    dialog.reject()
    assert dialog.choice == "dismissed"
    assert services.timer.get_active() is not None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("UNIQUE constraint failed: index 'ux_single_active'", "Ya hay una sesión activa"),
        ("FOREIGN KEY constraint failed", "inexistentes o en uso"),
        ("CHECK constraint failed: ck_entries_end_after_start", "anterior a la de inicio"),
        ("CHECK constraint failed: ck_entries_duration_nonnegative", "negativa"),
        ("UNIQUE constraint failed: projects.name", "Ya existe un proyecto"),
    ],
)
def test_raw_sqlite_errors_never_shown(raw, expected):
    message = user_message(sqlite3.IntegrityError(raw))
    assert expected in message
    assert "constraint" not in message.lower()


def test_unexpected_errors_get_generic_message():
    assert user_message(RuntimeError("SELECT * FROM boom")) == GENERIC
