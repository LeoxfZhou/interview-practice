from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .constants import APP_ID
from .database import (
    BASE_DIR,
    get_answer,
    get_bootstrap,
    get_progress_stats,
    get_quiz_progress,
    record_result,
    initialize_database,
    list_library_questions,
    list_library_sections,
    reset_progress,
    save_selection,
    save_selected_topics,
    select_next_question,
)


STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="面试答题本",
    description="面向 LLM Application Engineer 的本地面试练习工具",
    version="1.5.1",
    lifespan=lifespan,
)


@app.middleware("http")
async def prevent_stale_static_assets(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        # 本地页面体积很小；每次重新验证能避免新版 HTML 搭配旧版 CSS/JS。
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class TopicSelection(BaseModel):
    topics: list[str] = Field(default_factory=list, max_length=30)


class SelectionRequest(TopicSelection):
    content_scope: Literal["foundation", "combined"] = "combined"


class NextQuestionRequest(TopicSelection):
    content_scope: Literal["foundation", "combined"] = "combined"
    previous_id: Optional[str] = Field(default=None, max_length=100)
    excluded_ids: list[str] = Field(default_factory=list, max_length=10000)
    round_filter: Literal['remaining', 'wrong'] = 'remaining'


class LibraryRequest(TopicSelection):
    content_scope: Literal["foundation", "combined"] = "combined"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ResultRequest(SelectionRequest):
    result: Literal['correct', 'wrong', 'unrated']


@app.put('/api/questions/{question_id}/result')
def update_result(question_id: str, payload: ResultRequest) -> dict:
    try:
        get_quiz_progress(payload.topics, payload.content_scope)
        return {'stats': record_result(question_id, payload.result),
                'progress': get_quiz_progress(payload.topics, payload.content_scope)}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


class LibrarySectionsRequest(TopicSelection):
    content_scope: Literal["foundation", "combined"] = "combined"
    result_filter: Literal['all', 'correct', 'wrong'] = 'all'


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_ID}


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    return get_bootstrap()


@app.put("/api/settings/topics")
def update_topics(payload: TopicSelection) -> dict[str, list[str]]:
    try:
        saved = save_selected_topics(payload.topics)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"selected_topics": saved}


@app.put("/api/settings/selection")
def update_selection(payload: SelectionRequest) -> dict:
    try:
        return save_selection(payload.topics, payload.content_scope)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/quiz/next")
def next_question(payload: NextQuestionRequest) -> dict:
    try:
        question = select_next_question(
            payload.topics,
            previous_id=payload.previous_id,
            content_scope=payload.content_scope,
            excluded_ids=payload.excluded_ids,
            round_filter=payload.round_filter,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    progress = get_quiz_progress(payload.topics, payload.content_scope)
    return {"question": question, "stats": get_progress_stats(), "progress": progress,
            "completed": progress['total'] > 0 and progress['remaining'] == 0}


@app.get("/api/questions/{question_id}/answer")
def answer(question_id: str) -> dict[str, str]:
    result = get_answer(question_id)
    if result is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return result


@app.post("/api/library/questions")
def library_questions(payload: LibraryRequest) -> dict:
    try:
        return list_library_questions(
            payload.topics,
            page=payload.page,
            page_size=payload.page_size,
            content_scope=payload.content_scope,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/library/sections")
def library_sections(payload: LibrarySectionsRequest) -> dict:
    try:
        result = list_library_sections(payload.topics, payload.content_scope, result_filter=payload.result_filter)
        result['progress'] = get_quiz_progress(payload.topics, payload.content_scope)
        result['stats'] = get_progress_stats()
        return result
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/progress/reset")
def reset_all_progress() -> dict:
    reset_progress()
    return {"ok": True, "stats": get_progress_stats()}
