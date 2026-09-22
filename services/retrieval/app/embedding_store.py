"""DINOv2 reference embeddings stored in PostgreSQL (pgvector).

Embeddings are keyed by image content (sha256) and model identifier, so they
survive dataset versions and are computed once per image. Queries are scoped
to one index build so the embedding shortlist and the SIFT index always see
the same set of references. Search is exact (no ANN index): the catalog holds
a few thousand vectors.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import psycopg
from pgvector.psycopg import register_vector


class EmbeddingStore:
    def __init__(self, database_url: str, model: str) -> None:
        self.database_url = database_url
        self.model = model
        self._connection: psycopg.Connection | None = None

    def _connect(self) -> psycopg.Connection:
        if self._connection is None or self._connection.closed:
            self._connection = psycopg.connect(self.database_url, autocommit=True)
            register_vector(self._connection)
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def missing(self, shas: Iterable[str]) -> set[str]:
        wanted = sorted(set(shas))
        if not wanted:
            return set()
        present = self._connect().execute(
            "SELECT image_sha256 FROM image_embeddings WHERE model = %s AND image_sha256 = ANY(%s)",
            (self.model, wanted),
        ).fetchall()
        return set(wanted) - {row[0] for row in present}

    def upsert_many(self, rows: list[tuple[str, np.ndarray]]) -> None:
        if not rows:
            return
        with self._connect().cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO image_embeddings (image_sha256, model, embedding)
                VALUES (%s, %s, %s)
                ON CONFLICT (image_sha256, model) DO NOTHING
                """,
                [(sha, self.model, np.asarray(vector, dtype=np.float32)) for sha, vector in rows],
            )

    def nearest(self, build_id: int, query: np.ndarray, limit: int) -> list[tuple[str, float]]:
        rows = self._connect().execute(
            """
            SELECT ir.slug, 1 - (e.embedding <=> %(q)s) AS similarity
            FROM index_references ir
            JOIN image_embeddings e ON e.image_sha256 = ir.image_sha256 AND e.model = %(model)s
            WHERE ir.build_id = %(build_id)s
            ORDER BY e.embedding <=> %(q)s, ir.slug
            LIMIT %(limit)s
            """,
            {"q": np.asarray(query, dtype=np.float32), "model": self.model, "build_id": build_id, "limit": limit},
        ).fetchall()
        return [(str(slug), float(similarity)) for slug, similarity in rows]

    def scores(self, build_id: int, query: np.ndarray, slugs: Iterable[str]) -> dict[str, float]:
        wanted = sorted(set(slugs))
        if not wanted:
            return {}
        rows = self._connect().execute(
            """
            SELECT ir.slug, 1 - (e.embedding <=> %(q)s) AS similarity
            FROM index_references ir
            JOIN image_embeddings e ON e.image_sha256 = ir.image_sha256 AND e.model = %(model)s
            WHERE ir.build_id = %(build_id)s AND ir.slug = ANY(%(slugs)s)
            """,
            {"q": np.asarray(query, dtype=np.float32), "model": self.model, "build_id": build_id,
             "slugs": wanted},
        ).fetchall()
        return {str(slug): float(similarity) for slug, similarity in rows}
