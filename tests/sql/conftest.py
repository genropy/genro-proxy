# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Test fixtures for SQL tests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from proxy.sql import SqlDb


@pytest_asyncio.fixture
async def sqlite_db() -> AsyncGenerator[SqlDb, None]:
    """Create a SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = SqlDb(db_path)
        await db.connect()
        yield db
        await db.close()
