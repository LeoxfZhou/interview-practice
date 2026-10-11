from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from app.main import (
    LibraryRequest,
    LibrarySectionsRequest,
    NextQuestionRequest,
    SelectionRequest,
    STATIC_DIR,
    app,
    library_questions,
    library_sections,
    next_question,
    prevent_stale_static_assets,
    reset_all_progress,
    update_selection,
)


class StaticAssetCacheTests(unittest.TestCase):
    @staticmethod
    def apply_cache_middleware(path: str) -> Response:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "server": ("testserver", 80),
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
            }
        )

        async def call_next(_request: Request) -> Response:
            return Response()

        return asyncio.run(prevent_stale_static_assets(request, call_next))

    def test_home_uses_versioned_static_assets_and_disables_cache(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        response = self.apply_cache_middleware("/")
        self.assertIn('/static/styles.css?v=1.6.0', html)
        self.assertIn('/static/app.js?v=1.6.0', html)
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(app.version, "1.6.0")

    def test_header_uses_brand_mark_for_directory_and_exposes_reset(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="brandMarkButton"', html)
        self.assertIn('id="drawerHomeButton"', html)
        self.assertIn('id="resetProgressButton"', html)
        self.assertNotIn('id="directoryButton"', html)

    def test_static_assets_disable_cache_but_api_behavior_is_unchanged(self) -> None:
        stylesheet = self.apply_cache_middleware("/static/styles.css")
        self.assertEqual(
            stylesheet.headers["cache-control"], "no-store, max-age=0"
        )
        self.assertEqual(stylesheet.headers["pragma"], "no-cache")

        health = self.apply_cache_middleware("/api/health")
        self.assertNotIn("cache-control", health.headers)


class LibraryApiTests(unittest.TestCase):
    def test_library_request_validates_pagination(self) -> None:
        with self.assertRaises(ValidationError):
            LibraryRequest(topics=["rag"], page=0)
        with self.assertRaises(ValidationError):
            LibraryRequest(topics=["rag"], page_size=101)

    @patch("app.main.list_library_questions")
    def test_library_endpoint_forwards_valid_request(self, query) -> None:
        query.return_value = {
            "items": [],
            "total": 0,
            "page": 2,
            "page_size": 20,
            "total_pages": 0,
        }
        result = library_questions(
            LibraryRequest(topics=["python", "rag"], page=2, page_size=20)
        )
        query.assert_called_once_with(
            ["python", "rag"], page=2, page_size=20, content_scope="combined"
        )
        self.assertEqual(result["page"], 2)

    @patch("app.main.list_library_questions", side_effect=ValueError("未知方向"))
    def test_library_endpoint_maps_domain_errors_to_422(self, _query) -> None:
        with self.assertRaises(HTTPException) as raised:
            library_questions(LibraryRequest(topics=["unknown"]))
        self.assertEqual(raised.exception.status_code, 422)

    @patch("app.main.save_selection")
    def test_selection_endpoint_saves_scope_and_topics_together(self, save) -> None:
        save.return_value = {"selected_topics": [], "content_scope": "foundation"}
        result = update_selection(SelectionRequest(topics=[], content_scope="foundation"))
        save.assert_called_once_with([], "foundation")
        self.assertEqual(result["content_scope"], "foundation")

    @patch('app.main.get_progress_stats', return_value={})
    @patch('app.main.get_quiz_progress', return_value={})
    @patch("app.main.list_library_sections")
    def test_sections_endpoint_forwards_scope(self, query, scoped, stats) -> None:
        query.return_value = {"sections": [], "total": 0}
        result = library_sections(
            LibrarySectionsRequest(topics=["ml"], content_scope="foundation")
        )
        query.assert_called_once_with(["ml"], "foundation", result_filter='all')
        self.assertEqual(result["total"], 0)

    def test_invalid_content_scope_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SelectionRequest(topics=[], content_scope="invalid")


class ProgressApiTests(unittest.TestCase):
    @patch('app.main.get_quiz_progress', return_value={'total': 20, 'correct': 0, 'remaining': 20})
    @patch("app.main.get_progress_stats")
    @patch("app.main.select_next_question")
    def test_next_question_returns_fresh_progress(self, select, progress, scope_progress) -> None:
        select.return_value = {"stable_id": "question-1", "prompt": "test"}
        progress.return_value = {"studied": 12, "total": 160}

        result = next_question(NextQuestionRequest(topics=["python"]))

        self.assertEqual(result["question"]["stable_id"], "question-1")
        self.assertEqual(result["stats"], {"studied": 12, "total": 160})
        progress.assert_called_once_with()

    @patch("app.main.get_progress_stats")
    @patch("app.main.reset_progress")
    def test_reset_returns_zeroed_progress(self, reset, progress) -> None:
        progress.return_value = {"studied": 0, "total": 160}

        result = reset_all_progress()

        reset.assert_called_once_with()
        self.assertEqual(
            result,
            {"ok": True, "stats": {"studied": 0, "total": 160}},
        )


if __name__ == "__main__":
    unittest.main()
