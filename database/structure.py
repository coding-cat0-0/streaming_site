from typing import Any, Generator
from sqlmodel import create_engine, Session

database_url = "sqlite:///./data.db"
 
engine = create_engine(
    database_url,
    echo=True,
    connect_args={"check_same_thread": False})

def get_session() -> Generator[Session, Any, None]:
    with Session(engine) as session:
        yield session