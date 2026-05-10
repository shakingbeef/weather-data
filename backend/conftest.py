"""Shared test fixtures for the weather-data backend."""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

import database


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    """Redirect database to a temporary path for every test."""
    db_path = tmp_path / "test_weather.db"
    with patch.object(database, "DB_PATH", db_path):
        database.init_db()
        yield db_path
