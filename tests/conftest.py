import os
import tempfile

# Must be set before kmuted/Qt are imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["KMUTED_HOME"] = tempfile.mkdtemp(prefix="kmuted-test-")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
