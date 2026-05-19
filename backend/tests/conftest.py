"""Pytest fixtures — async DB session against the dev postgres.

Tests assume a running `make up` (postgres + redis). They wrap each test in a
transaction-style cleanup at the agent level so seed data is not contaminated.
"""
import asyncio
import os
import sys
import pytest_asyncio

# Make `backend/` importable when running `pytest backend/tests`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import AsyncSessionLocal  # noqa: E402


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
