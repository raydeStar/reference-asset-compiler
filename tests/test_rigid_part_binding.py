"""CPU-only, optional real-Blender contract test for explicit rigid part binding."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.environ.get('RAC_BLENDER'), reason='Set RAC_BLENDER for real Blender checks')
def test_rigid_parts_preserve_payload_and_reject_invalid_contracts(tmp_path):
    result = subprocess.run([
        os.environ['RAC_BLENDER'], '-b', '--factory-startup', '--threads', '4',
        '--python-exit-code', '1', '--python', str(ROOT / 'tests/fixtures/rigid_binding_fixture.py'),
        '--', str(ROOT), str(tmp_path),
    ], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'RIGID_BINDING_FIXTURE_OK' in result.stdout
