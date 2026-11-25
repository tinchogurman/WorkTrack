"""Render portfolio screenshots using temporary, fictional data only.

Run from the repository root: python tools/render_demo.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> None:
    # Set the data location before importing application modules.
    with tempfile.TemporaryDirectory(prefix="worktrack-demo-") as directory:
        root = Path(directory)
        os.environ["WORKTRACK_DATA_DIR"] = str(root)
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase
        from worktrack.core.clock import FakeClock
        from worktrack.services.context import AppServices
        from worktrack.services.entry_service import EntryDraft
        from worktrack.ui.main_window import MainWindow
        from worktrack.ui.theme import apply_theme

        clock = FakeClock(datetime(2026, 11, 25, 19, tzinfo=timezone.utc))
        app = QApplication([])
        # Windows' offscreen platform needs an explicitly loaded font.
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuil.ttf", "seguisb.ttf"):
            if (fonts / name).exists():
                QFontDatabase.addApplicationFont(str(fonts / name))
        apply_theme(app)
        services = AppServices.open(root / "demo.db", clock, timezone.utc, root / "backups")
        projects = [
            services.projects.create_project("Producto demo", "#3987E5"),
            services.projects.create_project("Aprendizaje", "#199E70"),
            services.projects.create_project("Diseño", "#D55181"),
        ]
        tasks = ["Desarrollo de funciones", "Pruebas y documentación", "Prototipos de interfaz"]
        for day in range(14):
            start = (clock.now() - timedelta(days=day)).replace(hour=9)
            for index, project in enumerate(projects):
                begin = start + timedelta(hours=index * 3)
                duration = timedelta(minutes=45 + ((day + index) % 4) * 20)
                services.entries.add_manual(EntryDraft(project.id, tasks[index], begin, begin + duration, "Datos ficticios para la demostración"))
        window = MainWindow(services, use_tray=False)
        window.resize(1400, 1280)
        window.show()
        output = Path(__file__).resolve().parents[1] / "docs" / "images"
        output.mkdir(parents=True, exist_ok=True)
        for section, name in [(1, "dashboard"), (0, "timer")]:
            window.nav.setCurrentRow(section)
            app.processEvents()
            window.grab().save(str(output / f"{name}.png"))
        window.shutdown()
        window.close()
        services.close()
        app.quit()
        print(f"Screenshots with fictional data: {output}")


if __name__ == "__main__":
    main()
