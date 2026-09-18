"""Redis 短期上下文与 PostgreSQL/Elasticsearch 长期记忆。"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.settings import Settings
from app.integrations.semantic import EmbeddingGateway


class LayeredMemory:
    """记忆只辅助理解追问，不作为 Claim 或引用证据。"""

    def __init__(self, settings: Settings, embeddings: EmbeddingGateway, es_client: Any):
        self.settings = settings
        self.embeddings = embeddings
        self.es = es_client
        self._redis: Any | None = None
        self._redis_lock = threading.Lock()
        self._postgres_ready = False
        self._postgres_lock = threading.Lock()
        self._index_ready = False
        self._index_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.redis_url or (self.settings.postgres_dsn and self.embeddings.enabled))

    def load_context(
        self,
        owner: str,
        thread_id: str,
        objective: str,
        project_scope: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        short = self._load_short(owner, thread_id, limit)
        long_term = self._recall_long(owner, objective, project_scope, max(1, limit // 2))
        seen: set[str] = set()
        values = []
        for item in [*short, *long_term]:
            content = str(item.get("content", "")).strip()
            fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if not content or fingerprint in seen or content == objective.strip():
                continue
            seen.add(fingerprint)
            values.append(item)
        return values[-limit:]

    def remember_message(self, owner: str, thread_id: str, role: str, content: str) -> None:
        client = self._redis_client()
        if client is None or not content.strip():
            return
        payload = json.dumps(
            {
                "role": role,
                "content": content.strip()[:4000],
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        try:
            key = self._short_key(owner, thread_id)
            with client.pipeline() as pipe:
                pipe.rpush(key, payload)
                pipe.ltrim(key, -self.settings.short_memory_limit, -1)
                pipe.expire(key, self.settings.short_memory_ttl_seconds)
                pipe.execute()
        except Exception:
            return

    def remember_interaction(
        self,
        owner: str,
        thread_id: str,
        project_scope: str,
        question: str,
        result: dict[str, Any],
    ) -> None:
        if not self.settings.postgres_dsn or not self.embeddings.enabled:
            return
        candidates = [
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "crop": str(item.get("crop", "")),
            }
            for item in result.get("candidateEntities", [])[:5]
            if item.get("id") or item.get("name")
        ]
        candidate_names = [item["name"] for item in candidates if item["name"]]
        content = question.strip()[:2000]
        if candidate_names:
            content += "\n候选病虫害：" + "、".join(candidate_names)
        try:
            vector = self.embeddings.embed([content])[0]
            record = self._store_postgres(
                owner,
                thread_id,
                project_scope,
                self._memory_key(project_scope, candidates),
                content,
                {"candidateEntities": candidates},
            )
            self._index_memory(record, vector)
        except Exception:
            return

    def forget_session(self, owner: str, thread_id: str) -> None:
        client = self._redis_client()
        if client is not None:
            try:
                client.delete(self._short_key(owner, thread_id))
            except Exception:
                pass
        if not self.settings.postgres_dsn:
            return
        try:
            self._ensure_postgres()
            import psycopg

            with psycopg.connect(self.settings.postgres_dsn, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    rows = cursor.execute(
                        """
                        UPDATE agrigraph_memories
                           SET status='DELETED', updated_at=NOW()
                         WHERE owner_username=%s AND thread_id=%s AND status='ACTIVE'
                     RETURNING id
                        """,
                        (owner, thread_id),
                    ).fetchall()
            for row in rows:
                self._delete_index_document(str(row[0]))
        except Exception:
            return

    def _load_short(self, owner: str, thread_id: str, limit: int) -> list[dict[str, Any]]:
        client = self._redis_client()
        if client is None:
            return []
        try:
            values = client.lrange(self._short_key(owner, thread_id), -limit, -1)
            return [json.loads(value) for value in values]
        except Exception:
            return []

    def _recall_long(
        self, owner: str, objective: str, project_scope: str, limit: int
    ) -> list[dict[str, Any]]:
        if not self.settings.postgres_dsn or not self.embeddings.enabled:
            return []
        try:
            vector = self.embeddings.embed([objective.strip()])[0]
            response = self.es.request(
                "POST",
                f"/{self.settings.memory_index}/_search",
                json={
                    "size": limit,
                    "knn": {
                        "field": "vector",
                        "query_vector": vector,
                        "k": limit,
                        "num_candidates": max(20, limit * 5),
                        "filter": {
                            "bool": {
                                "filter": [
                                    {"term": {"ownerUsername": owner}},
                                    {"term": {"projectScope": project_scope}},
                                    {"term": {"status": "ACTIVE"}},
                                ],
                                "should": [
                                    {"bool": {"must_not": {"exists": {"field": "expiresAt"}}}},
                                    {"range": {"expiresAt": {"gt": "now"}}},
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    },
                    "_source": ["id", "threadId", "content", "version", "metadata"],
                },
            )
            hits = response.get("hits", {}).get("hits", [])
            return [
                {
                    "role": "memory",
                    "content": str(hit.get("_source", {}).get("content", "")),
                    "metadata": {
                        "memoryId": hit.get("_source", {}).get("id"),
                        "threadId": hit.get("_source", {}).get("threadId"),
                        "version": hit.get("_source", {}).get("version"),
                        "score": float(hit.get("_score") or 0.0),
                    },
                }
                for hit in hits
            ]
        except Exception:
            return []

    def _store_postgres(
        self,
        owner: str,
        thread_id: str,
        project_scope: str,
        memory_key: str,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_postgres()
        import psycopg
        from psycopg.types.json import Jsonb

        memory_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.settings.memory_ttl_days)
        superseded_ids: list[str] = []
        with psycopg.connect(self.settings.postgres_dsn, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                rows = cursor.execute(
                    """
                    SELECT id, version
                      FROM agrigraph_memories
                     WHERE owner_username=%s AND project_scope=%s AND memory_key=%s AND status='ACTIVE'
                     ORDER BY version DESC
                       FOR UPDATE
                    """,
                    (owner, project_scope, memory_key),
                ).fetchall()
                version = max((int(row[1]) for row in rows), default=0) + 1
                superseded_ids = [str(row[0]) for row in rows]
                if superseded_ids:
                    cursor.execute(
                        """
                        UPDATE agrigraph_memories
                           SET status='SUPERSEDED', updated_at=NOW()
                         WHERE id = ANY(%s::uuid[])
                        """,
                        (superseded_ids,),
                    )
                cursor.execute(
                    """
                    INSERT INTO agrigraph_memories(
                        id, owner_username, project_scope, thread_id, memory_key, content,
                        metadata, version, status, conflict_of, expires_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s)
                    """,
                    (
                        memory_id,
                        owner,
                        project_scope,
                        thread_id,
                        memory_key,
                        content,
                        Jsonb(metadata),
                        version,
                        superseded_ids[0] if superseded_ids else None,
                        expires_at,
                    ),
                )
                profile = {
                    "lastThreadId": thread_id,
                    "lastQuestion": content.splitlines()[0],
                    "candidateEntities": metadata.get("candidateEntities", []),
                }
                cursor.execute(
                    """
                    INSERT INTO agrigraph_user_profiles(owner_username, project_scope, profile, version)
                    VALUES (%s,%s,%s,1)
                    ON CONFLICT(owner_username, project_scope) DO UPDATE
                       SET profile=EXCLUDED.profile,
                           version=agrigraph_user_profiles.version + 1,
                           updated_at=NOW()
                    """,
                    (owner, project_scope, Jsonb(profile)),
                )
        for old_id in superseded_ids:
            self._delete_index_document(old_id)
        return {
            "id": memory_id,
            "ownerUsername": owner,
            "projectScope": project_scope,
            "threadId": thread_id,
            "memoryKey": memory_key,
            "content": content,
            "metadata": metadata,
            "version": version,
            "status": "ACTIVE",
            "expiresAt": expires_at.isoformat(),
        }

    def _ensure_postgres(self) -> None:
        if self._postgres_ready:
            return
        with self._postgres_lock:
            if self._postgres_ready:
                return
            import psycopg

            with psycopg.connect(self.settings.postgres_dsn, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS agrigraph_memories(
                            id UUID PRIMARY KEY,
                            owner_username TEXT NOT NULL,
                            project_scope TEXT NOT NULL,
                            thread_id TEXT NOT NULL,
                            memory_key TEXT NOT NULL,
                            content TEXT NOT NULL,
                            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                            version INTEGER NOT NULL,
                            status TEXT NOT NULL,
                            conflict_of UUID NULL,
                            expires_at TIMESTAMPTZ NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_agrigraph_memory_lookup
                            ON agrigraph_memories(owner_username, project_scope, memory_key, status)
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS agrigraph_user_profiles(
                            owner_username TEXT NOT NULL,
                            project_scope TEXT NOT NULL,
                            profile JSONB NOT NULL DEFAULT '{}'::jsonb,
                            version INTEGER NOT NULL DEFAULT 1,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY(owner_username, project_scope)
                        )
                        """
                    )
            self._postgres_ready = True

    def _index_memory(self, record: dict[str, Any], vector: list[float]) -> None:
        self._ensure_memory_index()
        self.es.request(
            "PUT",
            f"/{self.settings.memory_index}/_doc/{record['id']}",
            json={**record, "vector": vector},
        )

    def _ensure_memory_index(self) -> None:
        if self._index_ready:
            return
        with self._index_lock:
            if self._index_ready:
                return
            response = self.es.request("HEAD", f"/{self.settings.memory_index}", allow_not_found=True)
            if response is None:
                self.es.request(
                    "PUT",
                    f"/{self.settings.memory_index}",
                    json={
                        "mappings": {
                            "properties": {
                                "ownerUsername": {"type": "keyword"},
                                "projectScope": {"type": "keyword"},
                                "threadId": {"type": "keyword"},
                                "memoryKey": {"type": "keyword"},
                                "content": {"type": "text"},
                                "version": {"type": "integer"},
                                "status": {"type": "keyword"},
                                "expiresAt": {"type": "date"},
                                "metadata": {"type": "object", "enabled": False},
                                "vector": {
                                    "type": "dense_vector",
                                    "dims": self.settings.embedding_dimensions,
                                    "index": True,
                                    "similarity": "cosine",
                                },
                            }
                        }
                    },
                )
            self._index_ready = True

    def _delete_index_document(self, memory_id: str) -> None:
        try:
            self.es.request(
                "DELETE",
                f"/{self.settings.memory_index}/_doc/{memory_id}",
                allow_not_found=True,
            )
        except Exception:
            return

    def _redis_client(self) -> Any | None:
        if not self.settings.redis_url:
            return None
        if self._redis is not None:
            return self._redis
        with self._redis_lock:
            if self._redis is not None:
                return self._redis
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    self.settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            except Exception:
                return None
        return self._redis

    def close(self) -> None:
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass

    def _short_key(self, owner: str, thread_id: str) -> str:
        digest = hashlib.sha256(f"{owner}:{thread_id}".encode("utf-8")).hexdigest()
        return f"agrigraph:memory:short:{digest}"

    @staticmethod
    def _memory_key(project_scope: str, candidates: list[dict[str, str]]) -> str:
        primary = candidates[0].get("id") if candidates else "general"
        return f"{project_scope}:{primary or 'general'}"
