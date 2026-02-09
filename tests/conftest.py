import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture
def mock_subprocess(mocker):
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='',
        stderr=''
    )
    return mock_run

@pytest.fixture
def mock_popen(mocker):
    mock_popen = mocker.patch('subprocess.Popen')
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_popen.return_value = mock_process
    return mock_popen

@pytest.fixture
def temp_config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
