import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("DORI_RUN_OLLAMA_INTEGRATION") == "1":
        return

    skip_integration = pytest.mark.skip(
        reason="set DORI_RUN_OLLAMA_INTEGRATION=1 to run Ollama integration tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
