"""Lightweight Relational Knowledge Graph (Milestone M9 Phase 17).

Implements an efficient SQLite-backed relationship graph:
- Entities: Sources, Documents, Versions, Chunks, Claims, Vulnerabilities, CWEs, CAPECs, ATT&CK.
- Relationships:
    SOURCE -> DOCUMENT
    DOCUMENT -> VERSION
    DOCUMENT -> CHUNK
    CHUNK -> CLAIM
    CLAIM -> SUPPORTS -> CLAIM
    CLAIM -> CONTRADICTS -> CLAIM
    CLAIM -> REFERENCES -> CWE/CVE/RFC
    CLAIM -> RELATED_TO -> CLAIM
    VULNERABILITY -> MAPS_TO_CWE
    VULNERABILITY -> MAPS_TO_CAPEC
    VULNERABILITY -> MAPS_TO_ATTACK

Ensures complete relational traceability without external graph database dependencies.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.knowledge.canonical_models import KnowledgeRelation, KnowledgeRelationType


class KnowledgeGraphEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RelationalKnowledgeGraph:
    """SQLite-backed lightweight graph storage for cybersecurity knowledge entities."""

    def __init__(self, db_path: Path = Path("data/knowledge/knowledge_graph.db")) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES graph_nodes(node_id),
                    FOREIGN KEY(target_id) REFERENCES graph_nodes(node_id)
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_edge_source ON graph_edges(source_id)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_edge_target ON graph_edges(target_id)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_edge_rel ON graph_edges(relation_type)
            """)

    def add_node(self, node_id: str, node_type: str, label: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Adds or updates a node in the knowledge graph."""
        meta_json = json.dumps(metadata or {})
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO graph_nodes (node_id, node_type, label, metadata_json) VALUES (?, ?, ?, ?)",
                (node_id, node_type, label, meta_json),
            )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Adds a directed relation edge between two nodes."""
        edge_id = f"EDGE-{source_id}-{relation_type}-{target_id}"
        meta_json = json.dumps(metadata or {})
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO graph_edges
                (edge_id, source_id, target_id, relation_type, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (edge_id, source_id, target_id, relation_type, meta_json, now),
            )
        return edge_id

    def get_outgoing_edges(self, source_id: str, relation_type: Optional[str] = None) -> List[KnowledgeGraphEdge]:
        """Retrieves edges originating from source_id."""
        query = "SELECT * FROM graph_edges WHERE source_id = ?"
        params: List[Any] = [source_id]
        if relation_type:
            query += " AND relation_type = ?"
            params.append(relation_type)
        cursor = self.conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append(KnowledgeGraphEdge(
                edge_id=row["edge_id"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                relation_type=row["relation_type"],
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            ))
        return results

    def get_incoming_edges(self, target_id: str, relation_type: Optional[str] = None) -> List[KnowledgeGraphEdge]:
        """Retrieves edges pointing to target_id."""
        query = "SELECT * FROM graph_edges WHERE target_id = ?"
        params: List[Any] = [target_id]
        if relation_type:
            query += " AND relation_type = ?"
            params.append(relation_type)
        cursor = self.conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append(KnowledgeGraphEdge(
                edge_id=row["edge_id"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                relation_type=row["relation_type"],
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            ))
        return results

    def map_vulnerability(self, vuln_name: str, cwe_id: str, capec_id: Optional[str] = None, attack_id: Optional[str] = None) -> None:
        """Helper to establish taxonomy links for a vulnerability class."""
        self.add_node(vuln_name, "VULNERABILITY", vuln_name)
        self.add_node(cwe_id, "CWE", cwe_id)
        self.add_edge(vuln_name, cwe_id, KnowledgeRelationType.MAPS_TO_CWE.value)

        if capec_id:
            self.add_node(capec_id, "CAPEC", capec_id)
            self.add_edge(vuln_name, capec_id, KnowledgeRelationType.MAPS_TO_CAPEC.value)

        if attack_id:
            self.add_node(attack_id, "MITRE_ATTACK", attack_id)
            self.add_edge(vuln_name, attack_id, KnowledgeRelationType.MAPS_TO_ATTACK.value)
