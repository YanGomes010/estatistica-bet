"""
cache_manager.py - Sistema de Cache Local com SQLite

Regras de Cache:
  - Resultados de jogos passados: PERMANENTE (nunca expiram)
  - Classificação/Standings: TTL configurável (padrão 12h)
  - Calendário de jogos futuros: TTL configurável (padrão 6h)
  - Dados de jogadores/lesões: TTL configurável (padrão 6-24h)
  - Dados ao vivo: 60 segundos

Uso:
    from src.cache.cache_manager import CacheManager
    cache = CacheManager()
    cache.set("standings", "brasileirao_a_2026", data, ttl=43200)
    data = cache.get("standings", "brasileirao_a_2026")
"""
import json
import sqlite3
import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import DB_PATH, CACHE_TTL

logger = logging.getLogger(__name__)


class CacheManager:
    """Gerenciador de cache persistente usando SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------ #
    # INICIALIZAÇÃO
    # ------------------------------------------------------------------ #
    def _init_db(self):
        """Cria as tabelas de cache se não existirem."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key   TEXT PRIMARY KEY,
                    category    TEXT NOT NULL,
                    data        TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    expires_at  REAL,          -- NULL = permanente
                    hit_count   INTEGER DEFAULT 0,
                    data_type   TEXT DEFAULT 'json'   -- 'json' | 'csv'
                );

                CREATE INDEX IF NOT EXISTS idx_cache_category
                    ON cache(category);

                CREATE INDEX IF NOT EXISTS idx_cache_expires
                    ON cache(expires_at);

                CREATE TABLE IF NOT EXISTS cache_stats (
                    category    TEXT PRIMARY KEY,
                    total_hits  INTEGER DEFAULT 0,
                    total_miss  INTEGER DEFAULT 0,
                    last_access REAL
                );
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_key(category: str, identifier: str) -> str:
        raw = f"{category}::{identifier}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32] + f"__{category}__{identifier[:64]}"

    @staticmethod
    def _now() -> float:
        return time.time()

    def _resolve_ttl(self, category: str, ttl: Optional[int]) -> Optional[float]:
        """Retorna o timestamp de expiração ou None (permanente)."""
        if ttl is not None:
            return self._now() + ttl if ttl > 0 else None
        default = CACHE_TTL.get(category)
        if default is None:
            return None  # permanente
        return self._now() + default

    def _update_stats(self, category: str, hit: bool):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO cache_stats (category, total_hits, total_miss, last_access)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(category) DO UPDATE SET
                    total_hits  = total_hits  + excluded.total_hits,
                    total_miss  = total_miss  + excluded.total_miss,
                    last_access = excluded.last_access
            """, (category, 1 if hit else 0, 0 if hit else 1, self._now()))

    # ------------------------------------------------------------------ #
    # OPERAÇÕES PRINCIPAIS
    # ------------------------------------------------------------------ #
    def get(self, category: str, identifier: str) -> Optional[Any]:
        """
        Busca dado no cache. Retorna None se não existe ou expirou.
        Para DataFrames, retorna um DataFrame; para outros, retorna o objeto Python.
        """
        key = self._make_key(category, identifier)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data, expires_at, data_type, hit_count FROM cache WHERE cache_key = ?",
                (key,)
            ).fetchone()

        if row is None:
            self._update_stats(category, hit=False)
            logger.debug(f"[CACHE MISS] {category}::{identifier}")
            return None

        # Verifica expiração
        if row["expires_at"] is not None and self._now() > row["expires_at"]:
            self._delete(key)
            self._update_stats(category, hit=False)
            logger.debug(f"[CACHE EXPIRED] {category}::{identifier}")
            return None

        # Atualiza contador de hits
        with self._conn() as conn:
            conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (key,)
            )

        self._update_stats(category, hit=True)
        logger.debug(f"[CACHE HIT] {category}::{identifier} (hits: {row['hit_count']+1})")

        # Desserializa
        try:
            if row["data_type"] == "csv":
                from io import StringIO
                return pd.read_csv(StringIO(row["data"]))
            else:
                return json.loads(row["data"])
        except Exception as e:
            logger.error(f"Erro ao desserializar cache {category}::{identifier}: {e}")
            return None

    def set(
        self,
        category: str,
        identifier: str,
        data: Any,
        ttl: Optional[int] = None,
        permanent: bool = False,
    ):
        """
        Salva dado no cache.

        Args:
            category:   Tipo de dado (standings, fixtures, results, etc.)
            identifier: Chave única (ex: "brasileirao_a_2026")
            data:       Dado a salvar (dict, list, DataFrame)
            ttl:        Tempo de vida em segundos. None = usa default da categoria.
            permanent:  Se True, ignora TTL e salva permanentemente.
        """
        key = self._make_key(category, identifier)
        now = self._now()
        expires_at = None if permanent else self._resolve_ttl(category, ttl)

        # Serializa
        if isinstance(data, pd.DataFrame):
            serialized = data.to_csv(index=False)
            data_type = "csv"
        else:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
            data_type = "json"

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO cache (cache_key, category, data, created_at, expires_at, data_type)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data       = excluded.data,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    hit_count  = 0,
                    data_type  = excluded.data_type
            """, (key, category, serialized, now, expires_at, data_type))

        expiry_str = (
            "permanente" if expires_at is None
            else datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M")
        )
        logger.debug(f"[CACHE SET] {category}::{identifier} | expira: {expiry_str}")

    def exists(self, category: str, identifier: str) -> bool:
        """Verifica se um dado existe e ainda é válido no cache."""
        return self.get(category, identifier) is not None

    def invalidate(self, category: str, identifier: str):
        """Remove entrada específica do cache."""
        key = self._make_key(category, identifier)
        self._delete(key)
        logger.info(f"[CACHE INVALIDATED] {category}::{identifier}")

    def invalidate_category(self, category: str):
        """Remove todas as entradas de uma categoria."""
        with self._conn() as conn:
            count = conn.execute(
                "DELETE FROM cache WHERE category = ?", (category,)
            ).rowcount
        logger.info(f"[CACHE CLEARED] categoria '{category}': {count} entradas removidas")

    def purge_expired(self) -> int:
        """Remove todas as entradas expiradas. Retorna quantidade removida."""
        now = self._now()
        with self._conn() as conn:
            count = conn.execute(
                "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,)
            ).rowcount
        if count:
            logger.info(f"[CACHE PURGE] {count} entradas expiradas removidas")
        return count

    def _delete(self, cache_key: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))

    # ------------------------------------------------------------------ #
    # INSPEÇÃO E DIAGNÓSTICO
    # ------------------------------------------------------------------ #
    def stats(self) -> pd.DataFrame:
        """Retorna estatísticas de uso do cache."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT
                    c.category,
                    COUNT(*) AS total_entries,
                    SUM(CASE WHEN c.expires_at IS NULL THEN 1 ELSE 0 END) AS permanent,
                    SUM(CASE WHEN c.expires_at IS NOT NULL
                              AND c.expires_at > ? THEN 1 ELSE 0 END) AS valid,
                    SUM(CASE WHEN c.expires_at IS NOT NULL
                              AND c.expires_at <= ? THEN 1 ELSE 0 END) AS expired,
                    SUM(c.hit_count) AS total_hits,
                    COALESCE(s.total_miss, 0) AS total_misses
                FROM cache c
                LEFT JOIN cache_stats s ON s.category = c.category
                GROUP BY c.category
            """, (self._now(), self._now())).fetchall()
        return pd.DataFrame([dict(r) for r in rows])

    def list_entries(self, category: Optional[str] = None) -> pd.DataFrame:
        """Lista entradas do cache com metadados."""
        query = """
            SELECT
                category,
                SUBSTR(cache_key, 35) AS identifier,
                created_at,
                expires_at,
                hit_count,
                data_type,
                LENGTH(data) AS size_bytes
            FROM cache
        """
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        df = pd.DataFrame([dict(r) for r in rows])
        if not df.empty:
            df["created_at"] = pd.to_datetime(df["created_at"], unit="s")
            df["expires_at"] = pd.to_datetime(df["expires_at"], unit="s", errors="coerce")
        return df

    def __repr__(self):
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        return f"<CacheManager db={self.db_path} entries={n}>"


# Instância global (singleton simples)
_cache_instance: Optional[CacheManager] = None

def get_cache() -> CacheManager:
    """Retorna instância global do CacheManager."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance
