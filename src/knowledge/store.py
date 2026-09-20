"""Dedicated VAPT Knowledge Store (SQLite + FTS5).

Implements M3.5 per M3 Plan v2.3.8:
- Physical isolation from Target-Evidence store (evidence.db)
- Canonical document and chunk tables
- SQLite FTS5 full-text indexing with Porter stemming
- Deterministic lexical ranking with chunk_id tie-breaking
- Read-only connection mode for production runtime
"""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocumentFrontmatter,
    KnowledgeSourceType,
    KnowledgeType,
)

logger = logging.getLogger("m3.store")


class VaptStoreError(Exception):
    """Raised on store isolation violations or storage failures."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class VaptKnowledgeStore:
    """
    Dedicated storage engine for the VAPT security knowledge corpus.
    
    CRITICAL ARCHITECTURAL RULE:
    Strictly isolated from evidence.db. Under no circumstances may this store
    connect to or manipulate target evidence data.
    """

    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        self.read_only = read_only

        # Dual Store Separation Invariant Check
        if self.db_path.name.lower() == "evidence.db":
            raise VaptStoreError(
                "DUAL_STORE_SEPARATION_VIOLATION",
                "Cannot open evidence.db as VAPT knowledge store; target evidence and methodology must remain isolated.",
            )

        if not self.read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.db_path))
            self._init_schema()
        else:
            if not self.db_path.exists():
                raise VaptStoreError(
                    "DATABASE_NOT_FOUND",
                    f"Knowledge database does not exist at {self.db_path}",
                )
            # Open in read-only URI mode to prevent accidental runtime mutation
            uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)

        self.conn.row_factory = sqlite3.Row

    def _init_schema(self) -> None:
        """Initialize relational and FTS5 tables."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    license TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    normalized_body TEXT NOT NULL
                )
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    knowledge_type TEXT NOT NULL,
                    category_tags TEXT NOT NULL,
                    title TEXT NOT NULL,
                    section_heading TEXT NOT NULL,
                    content TEXT NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    trust_tier TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                )
            """)

            # SQLite FTS5 virtual table for lexical retrieval
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
                    chunk_id UNINDEXED,
                    title,
                    section_heading,
                    content,
                    category_tags,
                    tokenize = 'porter unicode61'
                )
            """)

    def insert_document(
        self,
        frontmatter: KnowledgeDocumentFrontmatter,
        normalized_body: str,
    ) -> None:
        """Insert or replace a corpus document record."""
        if self.read_only:
            raise VaptStoreError("READ_ONLY_VIOLATION", "Cannot insert into read-only store")

        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    document_id, title, source_name, source_version,
                    source_url, license, author, content_hash, normalized_body
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frontmatter.document_id,
                    frontmatter.title,
                    frontmatter.source_name,
                    frontmatter.source_version,
                    frontmatter.source_url,
                    frontmatter.license,
                    frontmatter.author,
                    frontmatter.content_hash,
                    normalized_body,
                ),
            )

    def insert_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None:
        """Insert chunks and synchronize FTS5 index."""
        if self.read_only:
            raise VaptStoreError("READ_ONLY_VIOLATION", "Cannot insert into read-only store")

        with self.conn:
            for chunk in chunks:
                tags_json = json.dumps(chunk.category_tags)
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                        chunk_id, document_id, source_type, knowledge_type,
                        category_tags, title, section_heading, content,
                        token_estimate, content_hash, trust_tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source_type.value,
                        chunk.knowledge_type.value,
                        tags_json,
                        chunk.title,
                        chunk.section_heading,
                        chunk.content,
                        chunk.token_estimate,
                        chunk.content_hash,
                        chunk.trust_tier,
                    ),
                )

                # Update FTS5 index
                self.conn.execute(
                    "DELETE FROM fts_chunks WHERE chunk_id = ?",
                    (chunk.chunk_id,),
                )
                self.conn.execute(
                    """
                    INSERT INTO fts_chunks (
                        chunk_id, title, section_heading, content, category_tags
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.title,
                        chunk.section_heading,
                        chunk.content,
                        " ".join(chunk.category_tags),
                    ),
                )

    def get_chunk(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        """Fetch chunk by ID."""
        cursor = self.conn.execute(
            """
            SELECT chunk_id, document_id, source_type, knowledge_type,
                   category_tags, title, section_heading, content,
                   token_estimate, content_hash, trust_tier
            FROM chunks WHERE chunk_id = ?
            """,
            (chunk_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_chunk(row)

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document metadata by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM documents WHERE document_id = ?",
            (document_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_chunks(self) -> List[KnowledgeChunk]:
        """Fetch all chunks ordered strictly by chunk_id ASC."""
        cursor = self.conn.execute(
            """
            SELECT chunk_id, document_id, source_type, knowledge_type,
                   category_tags, title, section_heading, content,
                   token_estimate, content_hash, trust_tier
            FROM chunks ORDER BY chunk_id ASC
            """
        )
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def get_chunk_count(self) -> int:
        """Return total number of chunks stored."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return int(cursor.fetchone()[0])

    def get_document_count(self) -> int:
        """Return total number of documents stored."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        return int(cursor.fetchone()[0])

    def query_lexical(
        self,
        query_text: str,
        top_k: int = 20,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        Execute FTS5 BM25 search with deterministic tie-breaking.
        
        Returns list of (KnowledgeChunk, score) pairs, where score is higher-is-better (-bm25),
        ordered strictly by score DESC, chunk_id ASC.
        """
        sanitized_query = self._sanitize_fts5_query(query_text)
        if not sanitized_query:
            return []

        # In SQLite FTS5, bm25() returns negative numbers where smaller/more negative is better.
        # We invert it (-bm25) so higher is better.
        # Chunk-level tie-breaking: chunk_id ASC per Section 19.1.
        sql = """
            SELECT c.chunk_id, c.document_id, c.source_type, c.knowledge_type,
                   c.category_tags, c.title, c.section_heading, c.content,
                   c.token_estimate, c.content_hash, c.trust_tier,
                   (-bm25(fts_chunks)) AS lexical_score
            FROM fts_chunks
            JOIN chunks c ON fts_chunks.chunk_id = c.chunk_id
            WHERE fts_chunks MATCH ?
            ORDER BY lexical_score DESC, c.chunk_id ASC
            LIMIT ?
        """
        try:
            cursor = self.conn.execute(sql, (sanitized_query, top_k))
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 query error on query '{sanitized_query}': {e}")
            return []

        results: List[Tuple[KnowledgeChunk, float]] = []
        for row in rows:
            chunk = self._row_to_chunk(row)
            score = float(row["lexical_score"])
            results.append((chunk, score))
        return results

    @staticmethod
    def _sanitize_fts5_query(query_text: str) -> str:
        """
        Sanitize freeform query text for safe FTS5 MATCH syntax:
        - Extract alphanumeric words
        - Join with OR or standard token match
        """
        raw_tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", query_text)
        if not raw_tokens:
            return ""
        # Quote any token containing a hyphen so FTS5 doesn't parse it as column negation
        tokens = [f'"{t}"' if "-" in t else t for t in raw_tokens]
        # Match any of the extracted significant terms
        return " OR ".join(tokens)

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> KnowledgeChunk:
        """Convert a database row into a KnowledgeChunk model."""
        tags = json.loads(row["category_tags"])
        return KnowledgeChunk(
            schema_version="3.0.0",
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            source_type=KnowledgeSourceType(row["source_type"]),
            knowledge_type=KnowledgeType(row["knowledge_type"]),
            category_tags=tags,
            title=row["title"],
            section_heading=row["section_heading"],
            content=row["content"],
            token_estimate=int(row["token_estimate"]),
            content_hash=row["content_hash"],
            trust_tier=row["trust_tier"],
        )

    def close(self) -> None:
        """Close SQLite database connection."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
