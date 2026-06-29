from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID
from editorial.models import (
    Article,
    ConstraintResult,
    EditorialStatus,
    Evaluation,
    Extraction,
    IssueProposal,
    WorkflowEvent,
)


class SQLiteArticleRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT UNIQUE, source TEXT,
                published_at TEXT, authors_json TEXT NOT NULL, summary TEXT, content TEXT,
                status TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)"
            )

    def upsert(self, article: Article) -> bool:
        with self._connect() as conn:
            if article.url is not None:
                existing = conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (str(article.url),)
                ).fetchone()
                if existing:
                    return False
            conn.execute(
                """INSERT INTO articles (id, title, url, source, published_at, authors_json, summary, content, status, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(article.id),
                    article.title,
                    str(article.url) if article.url else None,
                    article.source,
                    article.published_at.isoformat() if article.published_at else None,
                    json.dumps(article.authors),
                    article.summary,
                    article.content,
                    article.status.value,
                    json.dumps(article.metadata),
                    article.created_at.isoformat(),
                    article.updated_at.isoformat(),
                ),
            )
            return True

    def list(
        self, status: EditorialStatus | None = None, limit: int | None = None
    ) -> list[Article]:
        query = "SELECT * FROM articles"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY published_at DESC, created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_article(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
        return int(row["n"])

    def get(self, article_id: UUID) -> Article | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (str(article_id),)
            ).fetchone()
        return self._row_to_article(row) if row else None

    def _row_to_article(self, row: sqlite3.Row) -> Article:
        return Article.model_validate(
            {
                "id": row["id"],
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "published_at": row["published_at"],
                "authors": json.loads(row["authors_json"]),
                "summary": row["summary"],
                "content": row["content"],
                "status": row["status"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )


class SQLiteExtractionRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS extractions (
                id TEXT PRIMARY KEY, article_id TEXT NOT NULL, extractor TEXT NOT NULL,
                extractor_version TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(article_id, extractor, kind))""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_extractions_article_id ON extractions(article_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_extractions_extractor ON extractions(extractor)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_extractions_unique_article_extractor_kind ON extractions(article_id, extractor, kind)"
            )

    def insert(self, extraction: Extraction) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO extractions (id, article_id, extractor, extractor_version, kind, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id, extractor, kind) DO UPDATE SET
                    id = excluded.id,
                    extractor_version = excluded.extractor_version,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at""",
                (
                    str(extraction.id),
                    str(extraction.article_id),
                    extraction.extractor,
                    extraction.extractor_version,
                    extraction.kind,
                    json.dumps(extraction.payload),
                    extraction.created_at.isoformat(),
                ),
            )

    def list(self, article_id: UUID | None = None) -> list[Extraction]:
        query = "SELECT * FROM extractions"
        params: list[object] = []
        if article_id is not None:
            query += " WHERE article_id = ?"
            params.append(str(article_id))
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_extraction(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM extractions").fetchone()
        return int(row["n"])

    def _row_to_extraction(self, row: sqlite3.Row) -> Extraction:
        return Extraction.model_validate(
            {
                "id": row["id"],
                "article_id": row["article_id"],
                "extractor": row["extractor"],
                "extractor_version": row["extractor_version"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteEvaluationRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY, article_id TEXT NOT NULL, evaluator TEXT NOT NULL,
                evaluator_version TEXT, kind TEXT NOT NULL, criterion TEXT,
                score REAL, confidence REAL, rationale TEXT, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(article_id, evaluator, kind))""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evaluations_article_id ON evaluations(article_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evaluations_evaluator ON evaluations(evaluator)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluations_unique_article_evaluator_kind ON evaluations(article_id, evaluator, kind)"
            )

    def insert(self, evaluation: Evaluation) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO evaluations (id, article_id, evaluator, evaluator_version, kind, criterion, score, confidence, rationale, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id, evaluator, kind) DO UPDATE SET
                    id = excluded.id,
                    evaluator_version = excluded.evaluator_version,
                    criterion = excluded.criterion,
                    score = excluded.score,
                    confidence = excluded.confidence,
                    rationale = excluded.rationale,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at""",
                (
                    str(evaluation.id),
                    str(evaluation.article_id),
                    evaluation.evaluator,
                    evaluation.evaluator_version,
                    evaluation.kind,
                    evaluation.criterion,
                    evaluation.score,
                    evaluation.confidence,
                    evaluation.rationale,
                    json.dumps(evaluation.payload),
                    evaluation.created_at.isoformat(),
                ),
            )

    def list(self, article_id: UUID | None = None) -> list[Evaluation]:
        query = "SELECT * FROM evaluations"
        params: list[object] = []
        if article_id is not None:
            query += " WHERE article_id = ?"
            params.append(str(article_id))
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_evaluation(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM evaluations").fetchone()
        return int(row["n"])

    def _row_to_evaluation(self, row: sqlite3.Row) -> Evaluation:
        return Evaluation.model_validate(
            {
                "id": row["id"],
                "article_id": row["article_id"],
                "evaluator": row["evaluator"],
                "evaluator_version": row["evaluator_version"],
                "kind": row["kind"],
                "criterion": row["criterion"],
                "score": row["score"],
                "confidence": row["confidence"],
                "rationale": row["rationale"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteIssueProposalRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS issue_proposals (
                id TEXT PRIMARY KEY, optimiser TEXT NOT NULL, optimiser_version TEXT,
                article_ids_json TEXT NOT NULL, objective_value REAL NOT NULL,
                constraint_results_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_issue_proposals_created_at ON issue_proposals(created_at)"
            )

    def insert(self, proposal: IssueProposal) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO issue_proposals (id, optimiser, optimiser_version, article_ids_json, objective_value, constraint_results_json, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(proposal.id),
                    proposal.optimiser,
                    proposal.optimiser_version,
                    json.dumps(
                        [str(article_id) for article_id in proposal.article_ids]
                    ),
                    proposal.objective_value,
                    json.dumps(
                        [
                            result.model_dump(mode="json")
                            for result in proposal.constraint_results
                        ]
                    ),
                    json.dumps(proposal.metadata),
                    proposal.created_at.isoformat(),
                ),
            )

    def list(self, limit: int | None = None) -> list[IssueProposal]:
        query = "SELECT * FROM issue_proposals ORDER BY created_at DESC"
        params: list[object] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_issue_proposal(row) for row in rows]

    def get(self, proposal_id: UUID) -> IssueProposal | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM issue_proposals WHERE id = ?", (str(proposal_id),)
            ).fetchone()
        return self._row_to_issue_proposal(row) if row else None

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM issue_proposals").fetchone()
        return int(row["n"])

    def _row_to_issue_proposal(self, row: sqlite3.Row) -> IssueProposal:
        return IssueProposal.model_validate(
            {
                "id": row["id"],
                "optimiser": row["optimiser"],
                "optimiser_version": row["optimiser_version"],
                "article_ids": json.loads(row["article_ids_json"]),
                "objective_value": row["objective_value"],
                "constraint_results": [
                    ConstraintResult.model_validate(result)
                    for result in json.loads(row["constraint_results_json"])
                ],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteWorkflowEventRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS workflow_events (
                id TEXT PRIMARY KEY, artefact_type TEXT NOT NULL,
                artefact_id TEXT NOT NULL, event_type TEXT NOT NULL,
                actor TEXT, reason TEXT, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_events_artefact ON workflow_events(artefact_type, artefact_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_events_created_at ON workflow_events(created_at)"
            )

    def insert(self, event: WorkflowEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO workflow_events (id, artefact_type, artefact_id, event_type, actor, reason, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(event.id),
                    event.artefact_type,
                    str(event.artefact_id),
                    event.event_type,
                    event.actor,
                    event.reason,
                    json.dumps(event.payload),
                    event.created_at.isoformat(),
                ),
            )

    def list(
        self,
        artefact_type: str | None = None,
        artefact_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[WorkflowEvent]:
        query = "SELECT rowid, * FROM workflow_events"
        params: list[object] = []
        filters: list[str] = []
        if artefact_type is not None:
            filters.append("artefact_type = ?")
            params.append(artefact_type)
        if artefact_id is not None:
            filters.append("artefact_id = ?")
            params.append(str(artefact_id))
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at ASC, rowid ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_workflow_event(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM workflow_events").fetchone()
        return int(row["n"])

    def get(self, event_id: UUID) -> WorkflowEvent | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_events WHERE id = ?", (str(event_id),)
            ).fetchone()
        return self._row_to_workflow_event(row) if row else None

    def _row_to_workflow_event(self, row: sqlite3.Row) -> WorkflowEvent:
        return WorkflowEvent.model_validate(
            {
                "id": row["id"],
                "artefact_type": row["artefact_type"],
                "artefact_id": row["artefact_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "reason": row["reason"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )
