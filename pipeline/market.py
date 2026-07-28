"""跨资产行情快照，使用成熟的 yfinance 下载器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging

log = logging.getLogger("infoCollector")


DEFAULT_SYMBOLS = {
    "标普500": "^GSPC",
    "纳斯达克": "^IXIC",
    "恒生指数": "^HSI",
    "上证指数": "000001.SS",
    "美国10年期收益率": "^TNX",
    "美元指数": "DX-Y.NYB",
    "美元兑人民币": "CNY=X",
    "原油": "CL=F",
    "黄金": "GC=F",
    "铜": "HG=F",
    "比特币": "BTC-USD",
    "VIX": "^VIX",
}


@dataclass
class MarketMove:
    name: str
    symbol: str
    last: float
    change_1d: float | None = None
    change_5d: float | None = None


@dataclass
class MarketSnapshot:
    as_of: datetime = field(default_factory=datetime.now)
    moves: list[MarketMove] = field(default_factory=list)
    error: str = ""

    def to_markdown(self) -> str:
        if not self.moves:
            return f"> 行情快照暂不可用：{self.error or '无数据'}"
        rows = ["| 资产 | 最新 | 1日 | 5日 |", "|---|---:|---:|---:|"]
        for move in self.moves:
            rows.append(
                f"| {move.name} | {move.last:,.2f} | {self._pct(move.change_1d)} | {self._pct(move.change_5d)} |"
            )
        return "\n".join(rows)

    def to_prompt(self) -> str:
        if not self.moves:
            return "行情数据不可用，禁止猜测价格表现。"
        return "\n".join(
            f"{m.name}({m.symbol}): 最新{m.last:.2f}, 1日{self._pct(m.change_1d)}, 5日{self._pct(m.change_5d)}"
            for m in self.moves
        )

    @staticmethod
    def _pct(value: float | None) -> str:
        return "—" if value is None else f"{value:+.2f}%"


class MarketDataProvider:
    """下载少量日线数据；失败时返回可降级的快照，不阻断日报。"""

    def __init__(self, symbols: dict[str, str] | None = None, period: str = "10d"):
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.period = period

    def fetch(self) -> MarketSnapshot:
        snapshot = MarketSnapshot()
        if not self.symbols:
            snapshot.error = "未配置观察资产"
            return snapshot

        try:
            import yfinance as yf

            tickers = list(self.symbols.values())
            data = yf.download(
                tickers=tickers,
                period=self.period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
                timeout=20,
            )
            for name, symbol in self.symbols.items():
                close = self._close_series(data, symbol, len(tickers))
                if close is None:
                    continue
                values = [float(value) for value in close.dropna().tolist()]
                if not values:
                    continue
                snapshot.moves.append(
                    MarketMove(
                        name=name,
                        symbol=symbol,
                        last=values[-1],
                        change_1d=self._change(values, 1),
                        change_5d=self._change(values, 5),
                    )
                )
        except Exception as exc:
            snapshot.error = str(exc)
            log.warning(f"Market snapshot failed: {exc}")

        if not snapshot.moves and not snapshot.error:
            snapshot.error = "下载结果为空"
        return snapshot

    @staticmethod
    def _close_series(data, symbol: str, ticker_count: int):
        try:
            if ticker_count == 1:
                return data["Close"]
            return data[symbol]["Close"]
        except (KeyError, TypeError):
            try:
                # 兼容 yfinance 的另一种 MultiIndex 列顺序。
                return data["Close"][symbol]
            except (KeyError, TypeError):
                return None

    @staticmethod
    def _change(values: list[float], sessions: int) -> float | None:
        if len(values) <= sessions or values[-sessions - 1] == 0:
            return None
        return (values[-1] / values[-sessions - 1] - 1) * 100
