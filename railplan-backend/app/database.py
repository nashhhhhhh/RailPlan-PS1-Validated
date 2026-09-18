import os
from fastapi import HTTPException
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

@lru_cache
def engine():
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True,
                         connect_args={"options": "-c timezone=UTC -c search_path=railplan,public"})

def session():
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(503,"DATABASE_URL is not configured")
    with Session(engine()) as db:
        with db.begin():
            yield db
