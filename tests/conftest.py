from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # UI tests run headless

from datetime import datetime, timezone  # noqa: E402

import pytest

from worktrack.core.clock import FakeClock
from worktrack.db.connection import connect
from worktrack.db.migrations import migrate

T0 = datetime(2026, 3, 10, 13, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real %APPDATA%\\WorkTrack from tests."""
    monkeypatch.setenv("WORKTRACK_DATA_DIR", str(tmp_path / "appdata"))


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_file):
    connection = connect(db_file)
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def services(db_file, clock):
    from worktrack.services.context import AppServices

    svc = AppServices.open(db_file, clock)
    yield svc
    svc.close()


@pytest.fixture
def project(services):
    return services.projects.create_project("Data Engineering", "#22C55E")


@pytest.fixture
def other_project(services):
    return services.projects.create_project("Desarrollo Python", "#3B82F6")
