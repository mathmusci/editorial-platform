from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID
from editorial.models import (
    Article,
    ConstraintResult,
    EditorialStatus,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
    PublicationSection,
    Review,
    WorkflowEvent,
)


def connect_sqlite(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def dump_json(value: object) -> str:
    return json.dumps(value)


def load_json(value: str) -> Any:
    return json.loads(value)


class SQLiteArticleRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

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
                    dump_json(article.authors),
                    article.summary,
                    article.content,
                    article.status.value,
                    dump_json(article.metadata),
                    article.created_at.isoformat(),
                    article.updated_at.isoformat(),
                ),
            )
            return True

    def exists(self, article: Article) -> bool:
        with self._connect() as conn:
            if article.url is not None:
                existing = conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (str(article.url),)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM articles WHERE id = ?", (str(article.id),)
                ).fetchone()
        return existing is not None

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
                "authors": load_json(row["authors_json"]),
                "summary": row["summary"],
                "content": row["content"],
                "status": row["status"],
                "metadata": load_json(row["metadata_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )


class SQLiteExtractionRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

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
                    dump_json(extraction.payload),
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

    def get(self, extraction_id: UUID) -> Extraction | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM extractions WHERE id = ?", (str(extraction_id),)
            ).fetchone()
        return self._row_to_extraction(row) if row else None

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
                "payload": load_json(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteEvaluationRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

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
                    dump_json(evaluation.payload),
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

    def get(self, evaluation_id: UUID) -> Evaluation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluations WHERE id = ?", (str(evaluation_id),)
            ).fetchone()
        return self._row_to_evaluation(row) if row else None

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
                "payload": load_json(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteIssueProposalRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

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
                    dump_json([str(article_id) for article_id in proposal.article_ids]),
                    proposal.objective_value,
                    dump_json(
                        [
                            result.model_dump(mode="json")
                            for result in proposal.constraint_results
                        ]
                    ),
                    dump_json(proposal.metadata),
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
                "article_ids": load_json(row["article_ids_json"]),
                "objective_value": row["objective_value"],
                "constraint_results": [
                    ConstraintResult.model_validate(result)
                    for result in load_json(row["constraint_results_json"])
                ],
                "metadata": load_json(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteWorkflowEventRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

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
                    dump_json(event.payload),
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
                "payload": load_json(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteReviewRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY, artefact_type TEXT NOT NULL,
                artefact_id TEXT NOT NULL, reviewer TEXT NOT NULL,
                decision TEXT NOT NULL, comments TEXT, findings_json TEXT NOT NULL,
                recommendations_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reviews_artefact ON reviews(artefact_type, artefact_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at)"
            )

    def insert(self, review: Review) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reviews (id, artefact_type, artefact_id, reviewer, decision, comments, findings_json, recommendations_json, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(review.id),
                    review.artefact_type,
                    str(review.artefact_id),
                    review.reviewer,
                    review.decision.value,
                    review.comments,
                    dump_json(review.findings),
                    dump_json(review.recommendations),
                    dump_json(review.metadata),
                    review.created_at.isoformat(),
                ),
            )

    def get(self, review_id: UUID) -> Review | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = ?", (str(review_id),)
            ).fetchone()
        return self._row_to_review(row) if row else None

    def list(
        self,
        artefact_type: str | None = None,
        artefact_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[Review]:
        query = "SELECT rowid, * FROM reviews"
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
        return [self._row_to_review(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM reviews").fetchone()
        return int(row["n"])

    def _row_to_review(self, row: sqlite3.Row) -> Review:
        return Review.model_validate(
            {
                "id": row["id"],
                "artefact_type": row["artefact_type"],
                "artefact_id": row["artefact_id"],
                "reviewer": row["reviewer"],
                "decision": row["decision"],
                "comments": row["comments"],
                "findings": load_json(row["findings_json"]),
                "recommendations": load_json(row["recommendations_json"]),
                "metadata": load_json(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLitePublicationRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS publications (
                id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL,
                title TEXT NOT NULL, subtitle TEXT, sections_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publications_created_at ON publications(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publications_proposal_id ON publications(proposal_id)"
            )

    def insert(self, publication: Publication) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO publications (id, proposal_id, title, subtitle, sections_json, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(publication.id),
                    str(publication.proposal_id),
                    publication.title,
                    publication.subtitle,
                    dump_json(
                        [
                            section.model_dump(mode="json")
                            for section in publication.sections
                        ]
                    ),
                    dump_json(publication.metadata),
                    publication.created_at.isoformat(),
                ),
            )

    def get(self, publication_id: UUID) -> Publication | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM publications WHERE id = ?", (str(publication_id),)
            ).fetchone()
        return self._row_to_publication(row) if row else None

    def list(self, limit: int | None = None) -> list[Publication]:
        query = "SELECT * FROM publications ORDER BY created_at DESC"
        params: list[object] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_publication(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM publications").fetchone()
        return int(row["n"])

    def _row_to_publication(self, row: sqlite3.Row) -> Publication:
        return Publication.model_validate(
            {
                "id": row["id"],
                "proposal_id": row["proposal_id"],
                "title": row["title"],
                "subtitle": row["subtitle"],
                "sections": [
                    PublicationSection.model_validate(section)
                    for section in load_json(row["sections_json"])
                ],
                "metadata": load_json(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )


class SQLiteOptimisationRequestRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS optimisation_requests (
                id TEXT PRIMARY KEY, publication TEXT, strategy TEXT NOT NULL,
                settings_json TEXT NOT NULL, constraints_json TEXT NOT NULL,
                goals_json TEXT NOT NULL, preferences_json TEXT NOT NULL,
                created_by TEXT, parent_request_id TEXT, parent_proposal_id TEXT,
                metadata_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_optimisation_requests_created_at ON optimisation_requests(created_at)"
            )

    def insert(self, request: OptimisationRequest) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO optimisation_requests (id, publication, strategy, settings_json, constraints_json, goals_json, preferences_json, created_by, parent_request_id, parent_proposal_id, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(request.id),
                    request.publication,
                    request.strategy,
                    dump_json(request.settings),
                    dump_json(request.constraints),
                    dump_json(request.goals),
                    dump_json(request.preferences),
                    request.created_by,
                    str(request.parent_request_id)
                    if request.parent_request_id is not None
                    else None,
                    str(request.parent_proposal_id)
                    if request.parent_proposal_id is not None
                    else None,
                    dump_json(request.metadata),
                    request.created_at.isoformat(),
                ),
            )

    def get(self, request_id: UUID) -> OptimisationRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM optimisation_requests WHERE id = ?",
                (str(request_id),),
            ).fetchone()
        return self._row_to_optimisation_request(row) if row else None

    def list(self, limit: int | None = None) -> list[OptimisationRequest]:
        query = "SELECT * FROM optimisation_requests ORDER BY created_at DESC"
        params: list[object] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_optimisation_request(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM optimisation_requests"
            ).fetchone()
        return int(row["n"])

    def _row_to_optimisation_request(self, row: sqlite3.Row) -> OptimisationRequest:
        return OptimisationRequest.model_validate(
            {
                "id": row["id"],
                "publication": row["publication"],
                "strategy": row["strategy"],
                "settings": load_json(row["settings_json"]),
                "constraints": load_json(row["constraints_json"]),
                "goals": load_json(row["goals_json"]),
                "preferences": load_json(row["preferences_json"]),
                "created_by": row["created_by"],
                "parent_request_id": row["parent_request_id"],
                "parent_proposal_id": row["parent_proposal_id"],
                "metadata": load_json(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )
