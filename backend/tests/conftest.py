import pytest
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base
import app.database as app_db

# Must import all models so Base.metadata has complete table definitions
# before create_all() is called. Without these imports, columns added later
# (like gap_report) won't be present in the test schema.
import app.models.job  # noqa: F401
import app.models.user_profile  # noqa: F401
import app.models.match_score  # noqa: F401
import app.models.application_draft  # noqa: F401
import app.models.source  # noqa: F401

TEST_DB_FILE = "./test_temp.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

@pytest.fixture(autouse=True)
async def setup_test_db():
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    test_session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Override app database engine and session
    app_db.engine = test_engine
    app_db.AsyncSessionLocal = test_session_maker

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass
