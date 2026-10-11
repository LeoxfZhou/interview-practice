from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "interview.db"
SEED_PATH = DATA_DIR / "questions.json"
FOUNDATION_PATH = DATA_DIR / "foundations"
VALID_CONTENT_SCOPES = {"foundation", "combined"}
VALID_CONTENT_TYPES = {"foundation", "interview"}


TOPICS = [
    {
        "slug": "python",
        "label": "Python 工程",
        "description": "语言核心、异常、异步、测试与可维护代码",
        "stage": "S1",
        "accent": "#5167d9",
    },
    {
        "slug": "algorithm",
        "label": "数据结构与算法",
        "description": "复杂度、常用结构和高频解题思路",
        "stage": "S1",
        "accent": "#7157c8",
    },
    {
        "slug": "fundamentals",
        "label": "计算机基础、网络与 HTTP",
        "description": "网络请求、超时、幂等、重试与退避",
        "stage": "S1",
        "accent": "#596f9c",
    },
    {
        "slug": "ml",
        "label": "PyTorch 与深度学习",
        "description": "训练流程、泛化、数据处理和评测",
        "stage": "S2",
        "accent": "#ca6558",
    },
    {
        "slug": "transformer",
        "label": "NLP 与 Transformer",
        "description": "注意力、位置编码、模型架构与推理",
        "stage": "S2",
        "accent": "#c77c32",
    },
    {
        "slug": "llm",
        "label": "大模型应用",
        "description": "Prompt、模型 API、结构化输出与可靠调用",
        "stage": "S3",
        "accent": "#be486f",
    },
    {
        "slug": "rag",
        "label": "RAG 与评测",
        "description": "切分、检索、重排、生成和 Bad Case 分析",
        "stage": "S4 / S6",
        "accent": "#338c72",
    },
    {
        "slug": "agent",
        "label": "Agent、工作流与 MCP",
        "description": "工具调用、状态管理、循环控制与协议边界",
        "stage": "S7",
        "accent": "#8b6742",
    },
    {
        "slug": "backend",
        "label": "FastAPI 与 AI 后端",
        "description": "路由、依赖注入、数据契约、SSE 与测试",
        "stage": "S5",
        "accent": "#26839b",
    },
    {
        "slug": "database",
        "label": "数据库、SQL、pgvector 与 Redis",
        "description": "约束、索引、事务、向量查询与缓存一致性",
        "stage": "S5",
        "accent": "#3d7f7b",
    },
    {
        "slug": "deployment",
        "label": "Docker、部署与 CI/CD",
        "description": "容器、持久化、健康检查、质量门禁与回滚",
        "stage": "S8",
        "accent": "#5b718f",
    },
    {
        "slug": "ops",
        "label": "安全、可靠性与可观测性",
        "description": "权限、提示注入、日志指标、限流、降级与容量",
        "stage": "S8",
        "accent": "#4c758b",
    },
    {
        "slug": "system_design",
        "label": "系统设计与工程场景",
        "description": "后台任务、状态机、幂等、多租户与架构取舍",
        "stage": "S5 / S9",
        "accent": "#7d6758",
    },
    {
        "slug": "advanced",
        "label": "扩展能力与岗位加试",
        "description": "推理服务、量化、LoRA、微调评测与容量规划",
        "stage": "Optional",
        "accent": "#76558b",
    },
]


@contextmanager
def connect(database_path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(
    database_path: Path = DATABASE_PATH,
    seed_path: Path = SEED_PATH,
    foundation_path: Path | None = FOUNDATION_PATH,
) -> None:
    """创建表并幂等导入种子题库，不会清空已有答题统计。"""
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                slug TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                stage TEXT NOT NULL,
                accent TEXT NOT NULL,
                sort_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                stable_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                kind TEXT NOT NULL,
                stage TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'interview',
                primary_topic TEXT NOT NULL REFERENCES topics(slug),
                source_name TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_topics (
                question_id TEXT NOT NULL REFERENCES questions(stable_id) ON DELETE CASCADE,
                topic_slug TEXT NOT NULL REFERENCES topics(slug) ON DELETE CASCADE,
                PRIMARY KEY (question_id, topic_slug)
            );

            CREATE TABLE IF NOT EXISTS question_stats (
                question_id TEXT PRIMARY KEY REFERENCES questions(stable_id) ON DELETE CASCADE,
                seen_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_question_topics_topic
                ON question_topics(topic_slug, question_id);
            CREATE INDEX IF NOT EXISTS idx_question_stats_seen
                ON question_stats(seen_count, last_seen_at);
            """
        )

        for order, topic in enumerate(TOPICS):
            connection.execute(
                """
                INSERT INTO topics(slug, label, description, stage, accent, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    label = excluded.label,
                    description = excluded.description,
                    stage = excluded.stage,
                    accent = excluded.accent,
                    sort_order = excluded.sort_order
                """,
                (
                    topic["slug"],
                    topic["label"],
                    topic["description"],
                    topic["stage"],
                    topic["accent"],
                    order,
                ),
            )

        # CREATE TABLE IF NOT EXISTS 不会为旧表增加新列，因此需要显式做幂等迁移。
        _ensure_question_metadata_columns(connection)
        stat_columns = {row['name'] for row in connection.execute('PRAGMA table_info(question_stats)')}
        if 'result' not in stat_columns:
            connection.execute("ALTER TABLE question_stats ADD COLUMN result TEXT NOT NULL DEFAULT 'unrated'")
        _seed_questions(connection, seed_path)
        if foundation_path is not None and foundation_path.exists():
            foundation_files = (
                sorted(foundation_path.glob("*.json"))
                if foundation_path.is_dir()
                else [foundation_path]
            )
            for path in foundation_files:
                _seed_questions(connection, path)

        # 初次打开默认全选；之后只读取用户主动保存的方向。
        now = _utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO app_settings(key, value_json, updated_at)
            VALUES ('selected_topics', ?, ?)
            """,
            (json.dumps([topic["slug"] for topic in TOPICS]), now),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO app_settings(key, value_json, updated_at)
            VALUES ('content_scope', ?, ?)
            """,
            (json.dumps("combined"), now),
        )


def _ensure_question_metadata_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(questions)")
    }
    if "content_type" not in columns:
        connection.execute(
            "ALTER TABLE questions ADD COLUMN content_type TEXT NOT NULL DEFAULT 'interview'"
        )
    if "primary_topic" not in columns:
        connection.execute("ALTER TABLE questions ADD COLUMN primary_topic TEXT")

    # 旧数据的第一个方向就是历来最主要的归类；种子同步后会再用 JSON 的明确值覆盖。
    connection.execute(
        """
        UPDATE questions
        SET primary_topic = (
            SELECT qt.topic_slug
            FROM question_topics AS qt
            JOIN topics AS t ON t.slug = qt.topic_slug
            WHERE qt.question_id = questions.stable_id
            ORDER BY t.sort_order
            LIMIT 1
        )
        WHERE primary_topic IS NULL OR primary_topic = ''
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_content_type ON questions(content_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_primary_topic ON questions(primary_topic, stage, stable_id)"
    )


def _seed_questions(connection: sqlite3.Connection, seed_path: Path) -> None:
    if not seed_path.exists():
        raise FileNotFoundError(f"题库种子文件不存在：{seed_path}")

    records = json.loads(seed_path.read_text(encoding="utf-8"))
    valid_topics = {topic["slug"] for topic in TOPICS}
    now = _utc_now()

    for record in records:
        missing = {
            "id",
            "prompt",
            "answer",
            "difficulty",
            "kind",
            "stage",
            "topics",
            "content_type",
            "primary_topic",
            "source_name",
            "source_ref",
        } - record.keys()
        if missing:
            raise ValueError(f"题目 {record.get('id', '<unknown>')} 缺少字段：{sorted(missing)}")

        unknown_topics = set(record["topics"]) - valid_topics
        if unknown_topics:
            raise ValueError(f"题目 {record['id']} 使用了未知方向：{sorted(unknown_topics)}")
        if record["content_type"] not in VALID_CONTENT_TYPES:
            raise ValueError(
                f"题目 {record['id']} 使用了未知内容类型：{record['content_type']}"
            )
        if record["primary_topic"] not in record["topics"]:
            raise ValueError(f"题目 {record['id']} 的主方向必须包含在 topics 中")

        content_hash = hashlib.sha256(
            _normalize_prompt(record["prompt"]).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO questions(
                stable_id, prompt, answer, difficulty, kind, stage,
                content_type, primary_topic, source_name, source_ref,
                content_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stable_id) DO UPDATE SET
                prompt = excluded.prompt,
                answer = excluded.answer,
                difficulty = excluded.difficulty,
                kind = excluded.kind,
                stage = excluded.stage,
                content_type = excluded.content_type,
                primary_topic = excluded.primary_topic,
                source_name = excluded.source_name,
                source_ref = excluded.source_ref,
                content_hash = excluded.content_hash,
                updated_at = excluded.updated_at
            """,
            (
                record["id"],
                record["prompt"].strip(),
                record["answer"].strip(),
                record["difficulty"],
                record["kind"],
                record["stage"],
                record["content_type"],
                record["primary_topic"],
                record["source_name"],
                record["source_ref"],
                content_hash,
                now,
                now,
            ),
        )
        connection.execute(
            "DELETE FROM question_topics WHERE question_id = ?", (record["id"],)
        )
        connection.executemany(
            "INSERT INTO question_topics(question_id, topic_slug) VALUES (?, ?)",
            [(record["id"], topic_slug) for topic_slug in record["topics"]],
        )
        connection.execute(
            "INSERT OR IGNORE INTO question_stats(question_id) VALUES (?)",
            (record["id"],),
        )


def import_questions(
    records: Sequence[dict[str, Any]], database_path: Path = DATABASE_PATH
) -> dict[str, int]:
    """导入外部整理后的题目；按规范化题干去重，重复导入不会累加。"""
    valid_topics = {topic["slug"] for topic in TOPICS}
    imported = 0
    updated = 0
    skipped = 0

    with connect(database_path) as connection:
        for record in records:
            prompt = str(record.get("prompt", "")).strip()
            answer = str(record.get("answer", "")).strip()
            topic_slugs = list(dict.fromkeys(record.get("topics", [])))
            if not prompt or not answer or not topic_slugs:
                skipped += 1
                continue
            unknown_topics = set(topic_slugs) - valid_topics
            if unknown_topics:
                raise ValueError(f"题目“{prompt[:24]}”使用了未知方向：{sorted(unknown_topics)}")

            content_type = str(record.get("content_type", "interview"))
            primary_topic = str(record.get("primary_topic") or topic_slugs[0])
            if content_type not in VALID_CONTENT_TYPES:
                raise ValueError(f"题目“{prompt[:24]}”使用了未知内容类型")
            if content_type == "foundation" and (
                "content_type" not in record or "primary_topic" not in record
            ):
                raise ValueError("基础知识导入必须显式提供 content_type 和 primary_topic")
            if primary_topic not in topic_slugs:
                raise ValueError(f"题目“{prompt[:24]}”的主方向必须包含在 topics 中")

            content_hash = hashlib.sha256(
                _normalize_prompt(prompt).encode("utf-8")
            ).hexdigest()
            existing = connection.execute(
                "SELECT stable_id FROM questions WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            stable_id = (
                existing["stable_id"]
                if existing
                else str(record.get("id") or f"import-{content_hash[:16]}")
            )
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO questions(
                    stable_id, prompt, answer, difficulty, kind, stage,
                    content_type, primary_topic, source_name, source_ref,
                    content_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stable_id) DO UPDATE SET
                    prompt = excluded.prompt,
                    answer = excluded.answer,
                    difficulty = excluded.difficulty,
                    kind = excluded.kind,
                    stage = excluded.stage,
                    content_type = excluded.content_type,
                    primary_topic = excluded.primary_topic,
                    source_name = excluded.source_name,
                    source_ref = excluded.source_ref,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    stable_id,
                    prompt,
                    answer,
                    record.get("difficulty", "基础"),
                    record.get("kind", "导入题"),
                    record.get("stage", "自定义"),
                    content_type,
                    primary_topic,
                    record.get("source_name", "用户导入"),
                    record.get("source_ref", ""),
                    content_hash,
                    now,
                    now,
                ),
            )
            connection.execute(
                "DELETE FROM question_topics WHERE question_id = ?", (stable_id,)
            )
            connection.executemany(
                "INSERT INTO question_topics(question_id, topic_slug) VALUES (?, ?)",
                [(stable_id, slug) for slug in topic_slugs],
            )
            connection.execute(
                "INSERT OR IGNORE INTO question_stats(question_id) VALUES (?)",
                (stable_id,),
            )
            if existing:
                updated += 1
            else:
                imported += 1

    return {"imported": imported, "updated": updated, "skipped": skipped}


def get_bootstrap(database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    with connect(database_path) as connection:
        topic_rows = connection.execute(
            """
            SELECT t.slug, t.label, t.description, t.stage, t.accent,
                   COUNT(qt.question_id) AS question_count,
                   SUM(CASE WHEN q.content_type = 'foundation' THEN 1 ELSE 0 END)
                       AS foundation_count,
                   SUM(CASE WHEN q.content_type = 'interview' THEN 1 ELSE 0 END)
                       AS interview_count
            FROM topics AS t
            LEFT JOIN question_topics AS qt ON qt.topic_slug = t.slug
            LEFT JOIN questions AS q ON q.stable_id = qt.question_id
            GROUP BY t.slug
            ORDER BY t.sort_order
            """
        ).fetchall()
        selected = get_setting(connection, "selected_topics", [])
        content_scope = get_setting(connection, "content_scope", "combined")
        stats = _get_progress_stats(connection)
        return {
            "topics": [dict(row) for row in topic_rows],
            "selected_topics": selected,
            "content_scope": content_scope,
            "stats": stats,
        }


def get_progress_stats(database_path: Path = DATABASE_PATH) -> dict[str, int]:
    """返回总数、正确数及供旧接口兼容使用的出现题数。"""
    with connect(database_path) as connection:
        return _get_progress_stats(connection)


def _get_progress_stats(connection: sqlite3.Connection) -> dict[str, int]:
    total = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    studied = connection.execute(
        "SELECT COUNT(*) FROM question_stats WHERE seen_count > 0"
    ).fetchone()[0]
    correct = connection.execute("SELECT COUNT(*) FROM question_stats WHERE result = 'correct'").fetchone()[0]
    wrong = connection.execute("SELECT COUNT(*) FROM question_stats WHERE result = 'wrong'").fetchone()[0]
    return {"total": total, "studied": studied, "correct": correct, "wrong": wrong}


def record_result(question_id: str, result: str, database_path: Path = DATABASE_PATH) -> dict:
    if result not in {'correct', 'wrong', 'unrated'}:
        raise ValueError('无效评价')
    with connect(database_path) as connection:
        cursor = connection.execute('UPDATE question_stats SET result = ? WHERE question_id = ?', (result, question_id))
        if not cursor.rowcount:
            raise ValueError('题目不存在')
        return _get_progress_stats(connection)


def get_quiz_progress(topics: Sequence[str], content_scope: str = 'combined', database_path: Path = DATABASE_PATH) -> dict:
    with connect(database_path) as connection:
        _validate_selection(connection, topics, content_scope)
        where, params = _content_filter_sql(topics, content_scope)
        row = connection.execute(f"SELECT COUNT(*), COALESCE(SUM(qs.result = 'correct'), 0), COALESCE(SUM(qs.result = 'wrong'), 0) FROM questions q JOIN question_stats qs ON qs.question_id=q.stable_id {where}", params).fetchone()
        return {'total': row[0], 'correct': row[1], 'wrong': row[2], 'remaining': row[0] - row[1]}


def save_selected_topics(
    topic_slugs: Sequence[str], database_path: Path = DATABASE_PATH
) -> list[str]:
    unique_slugs = list(dict.fromkeys(topic_slugs))
    with connect(database_path) as connection:
        valid = {
            row[0]
            for row in connection.execute(
                "SELECT slug FROM topics WHERE slug IN ({})".format(
                    ",".join("?" for _ in unique_slugs) or "NULL"
                ),
                unique_slugs,
            )
        }
        unknown = set(unique_slugs) - valid
        if unknown:
            raise ValueError(f"未知方向：{sorted(unknown)}")
        set_setting(connection, "selected_topics", unique_slugs)
    return unique_slugs


def save_selection(
    topic_slugs: Sequence[str],
    content_scope: str,
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    unique_slugs = list(dict.fromkeys(topic_slugs))
    with connect(database_path) as connection:
        _validate_selection(connection, unique_slugs, content_scope)
        set_setting(connection, "selected_topics", unique_slugs)
        set_setting(connection, "content_scope", content_scope)
    return {"selected_topics": unique_slugs, "content_scope": content_scope}


def _validate_selection(
    connection: sqlite3.Connection,
    topic_slugs: Sequence[str],
    content_scope: str,
) -> None:
    if content_scope not in VALID_CONTENT_SCOPES:
        raise ValueError(f"未知内容范围：{content_scope}")
    unique_slugs = list(dict.fromkeys(topic_slugs))
    if not unique_slugs:
        return
    placeholders = ",".join("?" for _ in unique_slugs)
    valid = {
        row[0]
        for row in connection.execute(
            f"SELECT slug FROM topics WHERE slug IN ({placeholders})",
            unique_slugs,
        )
    }
    unknown = set(unique_slugs) - valid
    if unknown:
        raise ValueError(f"未知方向：{sorted(unknown)}")


def select_next_question(
    topic_slugs: Sequence[str],
    previous_id: str | None = None,
    content_scope: str = "combined",
    database_path: Path = DATABASE_PATH,
    excluded_ids: Sequence[str] = (),
    round_filter: str = 'remaining',
) -> dict[str, Any] | None:
    """每轮排除已出题，错题留到用户主动开始下一轮。"""
    if round_filter not in {'remaining', 'wrong'}:
        raise ValueError('无效复习范围')
    unique_slugs = list(dict.fromkeys(topic_slugs))

    with connect(database_path) as connection:
        _validate_selection(connection, unique_slugs, content_scope)
        where_sql, params = _content_filter_sql(unique_slugs, content_scope)
        where_sql += (" AND " if where_sql else "WHERE ") + "qs.result <> 'correct'"
        if round_filter == 'wrong':
            where_sql += " AND qs.result = 'wrong'"
        rows = connection.execute(
            f"""
            SELECT q.stable_id, q.prompt, q.difficulty, q.kind, q.stage,
                   q.content_type, q.primary_topic,
                   q.source_name, q.source_ref, qs.seen_count, qs.result,
                   GROUP_CONCAT(DISTINCT qt_all.topic_slug) AS topic_slugs
            FROM questions AS q
            JOIN question_stats AS qs ON qs.question_id = q.stable_id
            JOIN question_topics AS qt_all ON qt_all.question_id = q.stable_id
            {where_sql}
            GROUP BY q.stable_id
            """,
            params,
        ).fetchall()
        excluded = set(excluded_ids)
        rows = [row for row in rows if row['stable_id'] not in excluded]
        if not rows:
            return None

        pool_size = len(rows)
        candidates = [row for row in rows if row['stable_id'] != previous_id] or rows
        chosen = random.SystemRandom().choice(candidates)
        now = _utc_now()
        connection.execute(
            """
            UPDATE question_stats
            SET seen_count = seen_count + 1, last_seen_at = ?
            WHERE question_id = ?
            """,
            (now, chosen["stable_id"]),
        )

        result = dict(chosen)
        result["topics"] = result.pop("topic_slugs").split(",")
        result["cycle"] = chosen['seen_count'] + 1
        result["remaining_in_cycle"] = pool_size
        result["pool_size"] = pool_size
        result.pop("seen_count")
        return result


def _content_filter_sql(
    topic_slugs: Sequence[str], content_scope: str
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if content_scope == "foundation":
        clauses.append("q.content_type = 'foundation'")
    if topic_slugs:
        placeholders = ",".join("?" for _ in topic_slugs)
        clauses.append(
            f"""
            EXISTS (
                SELECT 1 FROM question_topics AS qt_filter
                WHERE qt_filter.question_id = q.stable_id
                  AND qt_filter.topic_slug IN ({placeholders})
            )
            """
        )
        params.extend(topic_slugs)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


def get_answer(question_id: str, database_path: Path = DATABASE_PATH) -> dict[str, str] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT stable_id, answer FROM questions WHERE stable_id = ?",
            (question_id,),
        ).fetchone()
        return dict(row) if row else None


def list_library_questions(
    topic_slugs: Sequence[str],
    page: int = 1,
    page_size: int = 20,
    content_scope: str = "combined",
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """分页返回题目和答案，不更新任何练习进度。"""
    unique_slugs = list(dict.fromkeys(topic_slugs))
    if page < 1:
        raise ValueError("页码必须从 1 开始")
    if not 1 <= page_size <= 100:
        raise ValueError("每页题数必须在 1 到 100 之间")

    with connect(database_path) as connection:
        _validate_selection(connection, unique_slugs, content_scope)
        where_clause, filter_params = _content_filter_sql(
            unique_slugs, content_scope
        )
        total = connection.execute(
            f"SELECT COUNT(*) FROM questions AS q {where_clause}",
            filter_params,
        ).fetchone()[0]
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size

        rows = connection.execute(
            f"""
            SELECT q.stable_id, q.prompt, q.answer, q.difficulty, q.kind,
                   q.stage, q.content_type, q.primary_topic,
                   q.source_name, q.source_ref,
                   (
                       SELECT GROUP_CONCAT(ordered_topics.slug)
                       FROM (
                           SELECT qt_all.topic_slug AS slug
                           FROM question_topics AS qt_all
                           JOIN topics AS t_all ON t_all.slug = qt_all.topic_slug
                           WHERE qt_all.question_id = q.stable_id
                           ORDER BY t_all.sort_order
                       ) AS ordered_topics
                   ) AS topic_slugs
            FROM questions AS q
            {where_clause}
            ORDER BY q.stage, q.stable_id
            LIMIT ? OFFSET ?
            """,
            [*filter_params, page_size, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["topics"] = item.pop("topic_slugs").split(",")
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


def list_library_sections(
    topic_slugs: Sequence[str],
    content_scope: str = "combined",
    database_path: Path = DATABASE_PATH,
    result_filter: str = 'all',
) -> dict[str, Any]:
    """一次返回全部匹配内容，并按唯一主方向分组。"""
    if result_filter not in {'all', 'correct', 'wrong'}:
        raise ValueError('无效评价筛选')
    unique_slugs = list(dict.fromkeys(topic_slugs))
    with connect(database_path) as connection:
        _validate_selection(connection, unique_slugs, content_scope)
        where_sql, params = _content_filter_sql(unique_slugs, content_scope)
        if result_filter != 'all':
            where_sql += (' AND ' if where_sql else 'WHERE ') + 'qs.result = ?'
            params.append(result_filter)
        rows = connection.execute(
            f"""
            SELECT q.stable_id, q.prompt, q.answer, q.difficulty, q.kind,
                   q.stage, q.content_type, q.primary_topic,
                   q.source_name, q.source_ref, qs.result,
                   (
                       SELECT GROUP_CONCAT(ordered_topics.slug)
                       FROM (
                           SELECT qt_all.topic_slug AS slug
                           FROM question_topics AS qt_all
                           JOIN topics AS t_all ON t_all.slug = qt_all.topic_slug
                           WHERE qt_all.question_id = q.stable_id
                           ORDER BY t_all.sort_order
                       ) AS ordered_topics
                   ) AS topic_slugs
            FROM questions AS q
            JOIN question_stats qs ON qs.question_id = q.stable_id
            {where_sql}
            ORDER BY q.stage, q.stable_id
            """,
            params,
        ).fetchall()

        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in rows:
            item = dict(row)
            item["topics"] = item.pop("topic_slugs").split(",")
            primary_topic = item["primary_topic"]
            grouped.setdefault(
                primary_topic, {"foundation": [], "interview": []}
            )[item["content_type"]].append(item)

        topic_by_slug = {topic["slug"]: topic for topic in TOPICS}
        sections = []
        for topic in TOPICS:
            groups_for_topic = grouped.get(topic["slug"])
            if not groups_for_topic:
                continue
            content_groups = []
            for content_type, label in (
                ("foundation", "基础知识"),
                ("interview", "面试题"),
            ):
                items = groups_for_topic[content_type]
                if not items:
                    continue
                content_groups.append(
                    {
                        "content_type": content_type,
                        "label": label,
                        "anchor_id": f"section-{topic['slug']}-{content_type}",
                        "count": len(items),
                        "items": items,
                    }
                )
            sections.append(
                {
                    "topic": {
                        key: topic_by_slug[topic["slug"]][key]
                        for key in ("slug", "label", "stage", "accent")
                    },
                    "count": sum(group["count"] for group in content_groups),
                    "groups": content_groups,
                }
            )

        return {
            "sections": sections,
            "total": len(rows),
            "content_scope": content_scope,
            "selected_topics": unique_slugs,
        }


def reset_progress(database_path: Path = DATABASE_PATH) -> None:
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE question_stats SET seen_count = 0, last_seen_at = NULL, result = 'unrated'"
        )


def get_setting(
    connection: sqlite3.Connection, key: str, default: Any
) -> Any:
    row = connection.execute(
        "SELECT value_json FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(connection: sqlite3.Connection, key: str, value: Any) -> None:
    connection.execute(
        """
        INSERT INTO app_settings(key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, ensure_ascii=False), _utc_now()),
    )


def _normalize_prompt(prompt: str) -> str:
    return "".join(prompt.lower().split()).rstrip("？?")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
