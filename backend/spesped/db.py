from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Reject naive writes and preserve UTC awareness with SQLite tests too."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("An aware instant is required")
            return value.astimezone(timezone.utc)
        return None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_session_factory(database_url: str):
    args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request):
    """Request scope; application services explicitly commit successful writes."""
    with request.app.state.session_factory() as db:
        yield db
