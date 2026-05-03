import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


class Ledger:
    """
    SQLite persistence layer for gradient translations.

    One ledger per novel. Indexed on normalized_text for O(log n) lookups.
    Supports atomic writes, resume, and fuzzy fallback for short clauses.
    """

    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                id              INTEGER PRIMARY KEY,
                original_text   TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                gradient        TEXT,
                stage           TEXT,
                budget_used     INTEGER DEFAULT 0,
                cluster_id      TEXT,
                occurrences     INTEGER DEFAULT 1,
                ledger_status   TEXT DEFAULT 'pending',
                created_at      TEXT,
                UNIQUE(normalized_text)
            );

            CREATE INDEX IF NOT EXISTS idx_normalized ON ledger(normalized_text);

            CREATE TABLE IF NOT EXISTS substitutions (
                ledger_id       INTEGER REFERENCES ledger(id),
                original_phrase TEXT,
                french_phrase   TEXT,
                type            TEXT,
                budget_cost     INTEGER
            );

            CREATE TABLE IF NOT EXISTS cluster_members (
                cluster_id  TEXT NOT NULL,
                clause_id   TEXT NOT NULL,
                ledger_id   INTEGER REFERENCES ledger(id),
                PRIMARY KEY (cluster_id, clause_id)
            );
            """
        )
        self._conn.commit()

    # ── Public interface ───────────────────────────────────────────────────────

    def lookup(self, text: str) -> Optional[Dict]:
        """Exact normalized lookup, then fuzzy fallback for short clauses."""
        normalized = self.normalize(text)

        row = self._conn.execute(
            "SELECT * FROM ledger WHERE normalized_text = ? AND ledger_status = 'complete'",
            (normalized,),
        ).fetchone()
        if row:
            return dict(row)

        if len(text.split()) <= 8:
            nl = len(normalized)
            candidates = self._conn.execute(
                """SELECT * FROM ledger
                   WHERE ledger_status = 'complete'
                     AND LENGTH(normalized_text) BETWEEN ? AND ?""",
                (max(0, nl - 4), nl + 4),
            ).fetchall()
            for candidate in candidates:
                if _edit_distance(normalized, candidate["normalized_text"]) <= 2:
                    return dict(candidate)

        return None

    def lookup_cluster_member(self, clause_id: str) -> Optional[Dict]:
        """Look up via cluster membership — for Pass 2 cluster-matched clauses."""
        row = self._conn.execute(
            """SELECT l.* FROM ledger l
               JOIN cluster_members cm ON cm.ledger_id = l.id
               WHERE cm.clause_id = ? AND l.ledger_status = 'complete'""",
            (clause_id,),
        ).fetchone()
        return dict(row) if row else None

    def write(
        self,
        original_text: str,
        result: Dict,
        cluster: Optional[Dict] = None,
    ) -> int:
        """Insert or update a ledger entry. Returns the row id."""
        normalized = self.normalize(original_text)
        now = datetime.utcnow().isoformat()
        cluster_id = cluster["cluster_id"] if cluster else None
        occurrences = cluster["total_occurrences"] if cluster else 1

        cur = self._conn.execute(
            """INSERT INTO ledger
                   (original_text, normalized_text, gradient, stage,
                    budget_used, cluster_id, occurrences, ledger_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', ?)
               ON CONFLICT(normalized_text) DO UPDATE SET
                   gradient      = excluded.gradient,
                   stage         = excluded.stage,
                   budget_used   = excluded.budget_used,
                   ledger_status = 'complete'""",
            (
                original_text,
                normalized,
                result.get("gradient", original_text),
                result.get("stage", ""),
                result.get("budget_used", 0),
                cluster_id,
                occurrences,
                now,
            ),
        )
        ledger_id = cur.lastrowid

        for sub in result.get("substitutions", []):
            self._conn.execute(
                """INSERT INTO substitutions
                       (ledger_id, original_phrase, french_phrase, type, budget_cost)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    ledger_id,
                    sub.get("original_phrase", ""),
                    sub.get("french_phrase", ""),
                    sub.get("type", ""),
                    sub.get("budget_cost", 0),
                ),
            )

        if cluster:
            for member in cluster.get("members", []):
                try:
                    self._conn.execute(
                        """INSERT OR IGNORE INTO cluster_members
                               (cluster_id, clause_id, ledger_id)
                           VALUES (?, ?, ?)""",
                        (cluster["cluster_id"], member["clause_id"], ledger_id),
                    )
                except Exception:
                    pass

        self._conn.commit()
        return ledger_id

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def normalize(text: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance — short strings only."""
    if abs(len(a) - len(b)) > 4:
        return 999
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            dp[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n]
