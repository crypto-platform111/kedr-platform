"""Portable test defaults: never open the installed user's application database."""
import os
import tempfile

import pytest


# main.py exposes a convenience app at import time. Keep that instance isolated
# even when a developer's shell points KEDR_DATA_DIR at their real installation.
_default_app_directory = tempfile.TemporaryDirectory(prefix="kedr-test-app-")
os.environ["KEDR_DATA_DIR"] = _default_app_directory.name
# Ordinary tests must never connect to a developer's hosted database or queue.
# Dedicated PostgreSQL cases use KEDR_TEST_POSTGRES_URL and explicit constructors.
os.environ.pop("KEDR_DATABASE_URL", None)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("KEDR_JOB_MODE", None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "local_archives: integration test requiring separately installed verified historical archives"
    )


def pytest_collection_modifyitems(items):
    from backend.app import data

    if data.MANIFEST is not None and data.MANIFEST.is_file():
        # Configured sources must pass their normal checksum/schema tests.
        # Do not turn corrupt or partially installed data into a false pass.
        return
    skip = pytest.mark.skip(reason="Optional verified historical archives are not installed; demo and fixture tests still run")
    for item in items:
        if "local_archives" in item.keywords:
            item.add_marker(skip)
