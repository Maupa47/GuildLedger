from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def spool():
    from guildledger.store import Spool

    s = Spool(":memory:")
    yield s
    s.close()
