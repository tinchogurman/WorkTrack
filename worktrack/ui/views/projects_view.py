"""Projects: create, edit, color, archive, delete (only if unused); and their tasks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.models import Project, Task
from worktrack.services.context import AppServices
from worktrack.ui import theme
from worktrack.ui.dialogs.project_dialog import ProjectDialog
from worktrack.ui.dialogs.task_dialog import TaskDialog
from worktrack.ui.errors import confirm, show_error
from worktrack.ui.icons import color_dot
from worktrack.ui.signals import AppSignals
from worktrack.ui.widgets import muted, page_title, section_title


def _style_archived(item: QListWidgetItem) -> None:
    font = QFont(item.font())
    font.setItalic(True)
    item.setFont(font)
    item.setForeground(QBrush(QColor(theme.MUTED)))


class ProjectsView(QWidget):
    def __init__(self, services: AppServices, signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.signals = signals
        self._build()
        signals.projects_changed.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(page_title("Projects"))

        splitter = QSplitter(Qt.Horizontal)

        # projects panel
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        head = QHBoxLayout()
        head.addWidget(section_title("Proyectos"))
        head.addStretch()
        self.show_archived_projects = QCheckBox("Mostrar archivados")
        self.show_archived_projects.toggled.connect(self.refresh)
        head.addWidget(self.show_archived_projects)
        lv.addLayout(head)
        self.project_list = QListWidget()
        self.project_list.currentItemChanged.connect(self._on_project_selected)
        self.project_list.itemDoubleClicked.connect(lambda _: self.edit_project())
        lv.addWidget(self.project_list, 1)
        pb = QHBoxLayout()
        self.new_project_btn = QPushButton("+ Nuevo proyecto")
        self.new_project_btn.setProperty("variant", "primary")
        self.new_project_btn.clicked.connect(self.new_project)
        self.edit_project_btn = QPushButton("Editar")
        self.edit_project_btn.clicked.connect(self.edit_project)
        self.archive_project_btn = QPushButton("Archivar")
        self.archive_project_btn.clicked.connect(self.toggle_archive_project)
        self.delete_project_btn = QPushButton("Eliminar")
        self.delete_project_btn.setProperty("variant", "danger")
        self.delete_project_btn.clicked.connect(self.delete_project)
        for b in (self.new_project_btn, self.edit_project_btn, self.archive_project_btn, self.delete_project_btn):
            pb.addWidget(b)
        pb.addStretch()
        lv.addLayout(pb)

        # tasks panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        head2 = QHBoxLayout()
        self.tasks_title = section_title("Tareas")
        head2.addWidget(self.tasks_title)
        head2.addStretch()
        self.show_archived_tasks = QCheckBox("Mostrar archivadas")
        self.show_archived_tasks.toggled.connect(self._refresh_tasks)
        head2.addWidget(self.show_archived_tasks)
        rv.addLayout(head2)
        self.task_list = QListWidget()
        self.task_list.currentItemChanged.connect(self._update_buttons)
        self.task_list.itemDoubleClicked.connect(lambda _: self.edit_task())
        rv.addWidget(self.task_list, 1)
        tb = QHBoxLayout()
        self.new_task_btn = QPushButton("+ Nueva tarea")
        self.new_task_btn.clicked.connect(self.new_task)
        self.edit_task_btn = QPushButton("Editar")
        self.edit_task_btn.clicked.connect(self.edit_task)
        self.archive_task_btn = QPushButton("Archivar")
        self.archive_task_btn.clicked.connect(self.toggle_archive_task)
        self.delete_task_btn = QPushButton("Eliminar")
        self.delete_task_btn.setProperty("variant", "danger")
        self.delete_task_btn.clicked.connect(self.delete_task)
        for b in (self.new_task_btn, self.edit_task_btn, self.archive_task_btn, self.delete_task_btn):
            tb.addWidget(b)
        tb.addStretch()
        rv.addLayout(tb)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 520])
        root.addWidget(splitter, 1)
        note = muted(
            "Un proyecto o tarea con sesiones registradas no se puede eliminar: archivalo. "
            "Los archivados no se ofrecen en Timer, pero su historial se conserva."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        QShortcut(QKeySequence.Delete, self.project_list, self.delete_project, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence.Delete, self.task_list, self.delete_task, context=Qt.WidgetShortcut)

    # --- selection helpers -------------------------------------------------
    def selected_project(self) -> Project | None:
        item = self.project_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def selected_task(self) -> Task | None:
        item = self.task_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    # --- refresh -----------------------------------------------------------
    def refresh(self) -> None:
        current = self.selected_project()
        current_id = current.id if current else None
        try:
            projects = self.services.projects.list_projects(self.show_archived_projects.isChecked())
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.project_list.blockSignals(True)
        self.project_list.clear()
        select_row = 0
        for row, project in enumerate(projects):
            label = project.name + ("  (archivado)" if project.archived else "")
            item = QListWidgetItem(color_dot(project.color, 14), label)
            item.setData(Qt.UserRole, project)
            if project.archived:
                _style_archived(item)
            self.project_list.addItem(item)
            if project.id == current_id:
                select_row = row
        self.project_list.blockSignals(False)
        if projects:
            self.project_list.setCurrentRow(select_row)
        self._on_project_selected()

    def _on_project_selected(self, *_args) -> None:
        project = self.selected_project()
        self.tasks_title.setText(f"Tareas de «{project.name}»" if project else "Tareas")
        self._refresh_tasks()

    def _refresh_tasks(self) -> None:
        project = self.selected_project()
        current = self.selected_task()
        current_id = current.id if current else None
        self.task_list.blockSignals(True)
        self.task_list.clear()
        if project:
            tasks = self.services.projects.list_tasks(project.id, self.show_archived_tasks.isChecked())
            for task in tasks:
                label = task.name + ("  (archivada)" if task.archived else "")
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, task)
                if task.description:
                    item.setToolTip(task.description)
                if task.archived:
                    _style_archived(item)
                self.task_list.addItem(item)
                if task.id == current_id:
                    self.task_list.setCurrentItem(item)
        self.task_list.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self, *_args) -> None:
        project, task = self.selected_project(), self.selected_task()
        for b in (self.edit_project_btn, self.archive_project_btn, self.delete_project_btn):
            b.setEnabled(project is not None)
        self.archive_project_btn.setText("Desarchivar" if project and project.archived else "Archivar")
        self.new_task_btn.setEnabled(project is not None and not project.archived)
        for b in (self.edit_task_btn, self.archive_task_btn, self.delete_task_btn):
            b.setEnabled(task is not None)
        self.archive_task_btn.setText("Desarchivar" if task and task.archived else "Archivar")

    def _changed(self) -> None:
        self.signals.projects_changed.emit()
        self.signals.entries_changed.emit()  # names/colors shown in history

    # --- project actions ---------------------------------------------------
    def new_project(self) -> None:
        dialog = ProjectDialog(
            self.services.projects.create_project,
            color=self.services.projects.suggest_color(),
            parent=self,
        )
        if dialog.exec():
            self._changed()
            self._select_project_named(dialog.name_edit.text())

    def _select_project_named(self, name: str) -> None:
        wanted = " ".join(name.split()).casefold()
        for row in range(self.project_list.count()):
            if self.project_list.item(row).data(Qt.UserRole).name.casefold() == wanted:
                self.project_list.setCurrentRow(row)
                return

    def edit_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        dialog = ProjectDialog(
            lambda name, color: self.services.projects.update_project(project.id, name, color),
            name=project.name,
            color=project.color,
            title="Editar proyecto",
            parent=self,
        )
        if dialog.exec():
            self._changed()

    def toggle_archive_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        try:
            self.services.projects.set_project_archived(project.id, not project.archived)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self._changed()

    def delete_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        if not confirm(
            self,
            "Eliminar proyecto",
            f"¿Eliminar definitivamente el proyecto «{project.name}» y sus tareas?\n\n"
            "Solo es posible si no tiene sesiones registradas. Esta acción no se puede deshacer.",
            yes="Eliminar",
        ):
            return
        try:
            self.services.projects.delete_project(project.id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self._changed()

    # --- task actions ------------------------------------------------------
    def new_task(self) -> None:
        project = self.selected_project()
        if not project:
            return
        dialog = TaskDialog(
            lambda name, desc: self.services.projects.create_task(project.id, name, desc),
            project_name=project.name,
            parent=self,
        )
        if dialog.exec():
            self._changed()

    def edit_task(self) -> None:
        project, task = self.selected_project(), self.selected_task()
        if not (project and task):
            return
        dialog = TaskDialog(
            lambda name, desc: self.services.projects.update_task(task.id, name, desc),
            project_name=project.name,
            name=task.name,
            description=task.description or "",
            title="Editar tarea",
            parent=self,
        )
        if dialog.exec():
            self._changed()

    def toggle_archive_task(self) -> None:
        task = self.selected_task()
        if not task:
            return
        try:
            self.services.projects.set_task_archived(task.id, not task.archived)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self._changed()

    def delete_task(self) -> None:
        task = self.selected_task()
        if not task:
            return
        if not confirm(
            self,
            "Eliminar tarea",
            f"¿Eliminar definitivamente la tarea «{task.name}»?\n\n"
            "Solo es posible si no tiene sesiones registradas.",
            yes="Eliminar",
        ):
            return
        try:
            self.services.projects.delete_task(task.id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self._changed()
