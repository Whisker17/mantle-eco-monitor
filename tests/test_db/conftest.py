import pytest
from sqlalchemy import create_engine, inspect

from src.db.models import Base


@pytest.fixture()
def db_inspector(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    yield inspector
    engine.dispose()
