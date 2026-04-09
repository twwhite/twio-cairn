import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

import aiosqlite
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import get_db, run_migrations
from app.models import (
    EntryCreate,
    EntryResponse,
    LoginRequest,
    MessageResponse,
    TypeCreate,
    TypeResponse,
)

load_dotenv()

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY is not set in .env")


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    yield


# App
app = FastAPI(title="twio-cairn", lifespan=lifespan)


# Auth
async def require_session(
    session_token: Annotated[str | None, Cookie()] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    result = await db.execute(
        "SELECT token FROM sessions WHERE token = ?", (session_token,)
    )
    row = await result.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


# Auth routes
@app.post("/login", response_model=MessageResponse)
async def login(body: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    if API_KEY is not None and not secrets.compare_digest(body.api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    token = secrets.token_hex(32)
    await db.execute("INSERT INTO sessions (token) VALUES (?)", (token,))
    await db.commit()
    response = JSONResponse(content={"message": "logged in"})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


@app.post("/logout", response_model=MessageResponse)
async def logout(
    session_token: Annotated[str | None, Cookie()] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    if session_token:
        await db.execute("DELETE FROM sessions WHERE token = ?", (session_token,))
        await db.commit()
    response = JSONResponse(content={"message": "logged out"})
    response.delete_cookie("session_token")
    return response


# Type stuff
@app.get("/types", response_model=list[TypeResponse])
async def get_types(
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
):
    result = await db.execute("SELECT * FROM types ORDER BY name ASC")
    rows = await result.fetchall()
    return [dict(row) for row in rows]


@app.post("/types", response_model=TypeResponse, status_code=status.HTTP_201_CREATED)
async def create_type(
    body: TypeCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
):
    try:
        result = await db.execute(
            """
            INSERT INTO types (name, unit, value_type, default_value, icon)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
            """,
            (body.name, body.unit, body.value_type, body.default_value, body.icon),
        )
        row = await result.fetchone()
        await db.commit()
        return dict(row) if row is not None else None
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Type '{body.name}' already exists",
        )


@app.delete("/types/{type_id}", response_model=MessageResponse)
async def delete_type(
    type_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
):
    result = await db.execute("SELECT id FROM types WHERE id = ?", (type_id,))
    row = await result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Type not found"
        )
    await db.execute("DELETE FROM types WHERE id = ?", (type_id,))
    await db.commit()
    return {"message": "deleted"}


# Entry stuff
@app.get("/entries", response_model=list[EntryResponse])
async def get_entries(
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
    type_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    query = """
        SELECT
            e.id,
            e.type_id,
            t.name AS type_name,
            t.unit AS type_unit,
            e.value,
            e.notes,
            e.created_at
        FROM entries e
        JOIN types t ON e.type_id = t.id
        WHERE (:type_id IS NULL OR e.type_id = :type_id)
        ORDER BY e.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = await db.execute(
        query, {"type_id": type_id, "limit": limit, "offset": offset}
    )
    rows = await result.fetchall()
    return [dict(row) for row in rows]


@app.post("/entries", response_model=EntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    body: EntryCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
):
    result = await db.execute("SELECT id FROM types WHERE id = ?", (body.type_id,))
    row = await result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Type with id {body.type_id} not found",
        )
    result = await db.execute(
        """
        INSERT INTO entries (type_id, value, notes)
        VALUES (?, ?, ?)
        RETURNING
            id,
            type_id,
            (SELECT name FROM types WHERE id = type_id) AS type_name,
            (SELECT unit FROM types WHERE id = type_id) AS type_unit,
            value,
            notes,
            created_at
        """,
        (body.type_id, body.value, body.notes),
    )
    row = await result.fetchone()
    await db.commit()
    return dict(row) if row is not None else None


@app.delete("/entries/{entry_id}", response_model=MessageResponse)
async def delete_entry(
    entry_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: None = Depends(require_session),
):
    result = await db.execute("SELECT id FROM entries WHERE id = ?", (entry_id,))
    row = await result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found"
        )
    await db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    await db.commit()
    return {"message": "deleted"}


# Statics
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
