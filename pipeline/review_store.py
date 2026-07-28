"""本地观点账本：记录交易假设，并用后续行情做确定性复盘。"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

from models.article import Article
from pipeline.market import MarketMove, MarketSnapshot


OUTCOMES = {"pending", "supported", "contradicted", "inconclusive", "unavailable"}
MANUAL_OUTCOMES = {"supported", "contradicted", "inconclusive"}


class ThesisReviewStore:
    """SQLite-backed decision journal shared by the pipeline and local UI."""

    def __init__(self, path: str | Path, move_threshold_pct: float = 0.3):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.move_threshold_pct = abs(float(move_threshold_pct))
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS thesis_reviews (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    event_key TEXT NOT NULL DEFAULT '',
                    thesis TEXT NOT NULL DEFAULT '',
                    counter_argument TEXT NOT NULL DEFAULT '',
                    invalidation TEXT NOT NULL DEFAULT '',
                    review_metric TEXT NOT NULL DEFAULT '',
                    review_symbol TEXT NOT NULL DEFAULT '',
                    expected_direction TEXT NOT NULL DEFAULT 'observe',
                    review_horizon_days INTEGER NOT NULL DEFAULT 3,
                    baseline_value REAL,
                    baseline_as_of TEXT,
                    latest_value REAL,
                    latest_as_of TEXT,
                    price_change_pct REAL,
                    automatic_outcome TEXT NOT NULL DEFAULT 'pending',
                    evaluated_at TEXT,
                    manual_outcome TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    affected_assets_json TEXT NOT NULL DEFAULT '[]',
                    watch_signals_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS thesis_reviews_due_idx ON thesis_reviews(due_at, automatic_outcome)"
            )

    def capture_and_evaluate(
        self,
        signals: list[Article],
        market_snapshot: MarketSnapshot | None,
        as_of: datetime | None = None,
    ) -> None:
        check_time = self._aware(as_of or datetime.now().astimezone())
        moves = market_snapshot.moves if market_snapshot else []
        with self._connect() as connection:
            for article in signals:
                move = self._resolve_move(article, moves)
                horizon = max(1, min(30, int(article.review_horizon_days or 3)))
                review_id = f"{check_time.date().isoformat()}:{article.id}"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO thesis_reviews (
                        id, signal_id, created_at, due_at, title, source, event_key,
                        thesis, counter_argument, invalidation, review_metric,
                        review_symbol, expected_direction, review_horizon_days,
                        baseline_value, baseline_as_of, affected_assets_json,
                        watch_signals_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        article.id,
                        check_time.isoformat(),
                        (check_time + timedelta(days=horizon)).isoformat(),
                        article.title,
                        article.source,
                        article.event_key,
                        article.trading_logic or article.asset_impact,
                        article.counter_argument,
                        article.invalidation,
                        article.review_metric or (move.name if move else ""),
                        article.review_symbol or (move.symbol if move else ""),
                        self._direction(article.expected_direction),
                        horizon,
                        move.last if move else None,
                        market_snapshot.as_of.astimezone().isoformat() if move and market_snapshot else None,
                        json.dumps(article.affected_assets, ensure_ascii=False),
                        json.dumps(article.watch_signals, ensure_ascii=False),
                    ),
                )
            self._evaluate_pending(connection, moves, market_snapshot, check_time)

    def evaluate(self, market_snapshot: MarketSnapshot | None, as_of: datetime | None = None) -> None:
        check_time = self._aware(as_of or datetime.now().astimezone())
        moves = market_snapshot.moves if market_snapshot else []
        with self._connect() as connection:
            self._evaluate_pending(connection, moves, market_snapshot, check_time)

    def _evaluate_pending(
        self,
        connection: sqlite3.Connection,
        moves: list[MarketMove],
        snapshot: MarketSnapshot | None,
        check_time: datetime,
    ) -> None:
        by_symbol = {move.symbol: move for move in moves}
        rows = connection.execute(
            "SELECT * FROM thesis_reviews WHERE automatic_outcome IN ('pending', 'unavailable')"
        ).fetchall()
        for row in rows:
            move = by_symbol.get(row["review_symbol"])
            latest_as_of = snapshot.as_of.astimezone().isoformat() if move and snapshot else None
            change = self._change(row["baseline_value"], move.last if move else None)
            due = self._aware(datetime.fromisoformat(row["due_at"]))
            outcome = row["automatic_outcome"]
            evaluated_at = row["evaluated_at"]
            if check_time >= due:
                outcome = self._outcome(row["expected_direction"], change)
                evaluated_at = check_time.isoformat()
            connection.execute(
                """
                UPDATE thesis_reviews
                SET latest_value = ?, latest_as_of = ?, price_change_pct = ?,
                    automatic_outcome = ?, evaluated_at = ?
                WHERE id = ?
                """,
                (move.last if move else None, latest_as_of, change, outcome, evaluated_at, row["id"]),
            )

    def list_records(self, limit: int = 12) -> list[dict]:
        safe_limit = max(1, min(100, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM thesis_reviews ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [self._serialise(row) for row in rows]

    def get(self, review_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM thesis_reviews WHERE id = ?", (review_id,)).fetchone()
        return self._serialise(row) if row else None

    def update_manual(self, review_id: str, outcome: str, note: str = "") -> dict | None:
        manual_outcome = "" if outcome == "pending" else outcome
        if manual_outcome and manual_outcome not in MANUAL_OUTCOMES:
            raise ValueError(f"Unsupported outcome: {outcome}")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE thesis_reviews SET manual_outcome = ?, note = ? WHERE id = ?",
                (manual_outcome, note.strip()[:500], review_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(review_id)

    def summary(self) -> dict:
        counts = {key: 0 for key in OUTCOMES}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT CASE WHEN manual_outcome != '' THEN manual_outcome ELSE automatic_outcome END AS outcome,
                       COUNT(*) AS amount
                FROM thesis_reviews
                GROUP BY outcome
                """
            ).fetchall()
        for row in rows:
            counts[row["outcome"]] = row["amount"]
        return {"total": sum(counts.values()), **counts}

    def _serialise(self, row: sqlite3.Row) -> dict:
        value = dict(row)
        value["affected_assets"] = self._json_list(value.pop("affected_assets_json", "[]"))
        value["watch_signals"] = self._json_list(value.pop("watch_signals_json", "[]"))
        value["outcome"] = value["manual_outcome"] or value["automatic_outcome"]
        value["outcome_source"] = "manual" if value["manual_outcome"] else "automatic"
        return value

    @staticmethod
    def _resolve_move(article: Article, moves: list[MarketMove]) -> MarketMove | None:
        if article.review_symbol:
            exact = next((move for move in moves if move.symbol == article.review_symbol), None)
            if exact:
                return exact
        names = [article.review_metric, *article.affected_assets]
        for name in names:
            if not name:
                continue
            match = next((move for move in moves if move.name == name or move.symbol == name), None)
            if match:
                return match
        return None

    def _outcome(self, direction: str, change: float | None) -> str:
        if direction not in {"up", "down"} or change is None:
            return "unavailable" if change is None else "inconclusive"
        if abs(change) < self.move_threshold_pct:
            return "inconclusive"
        supports = change > 0 if direction == "up" else change < 0
        return "supported" if supports else "contradicted"

    @staticmethod
    def _direction(value: str) -> str:
        return value if value in {"up", "down", "observe"} else "observe"

    @staticmethod
    def _change(baseline: float | None, latest: float | None) -> float | None:
        if baseline in (None, 0) or latest is None:
            return None
        return round((latest / baseline - 1) * 100, 4)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.astimezone() if value.tzinfo is None else value.astimezone()

    @staticmethod
    def _json_list(value: str) -> list[str]:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
