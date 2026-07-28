"""从官方机器可读日程同步核心财经事件。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from filelock import FileLock
import httpx
from bs4 import BeautifulSoup
from icalendar import Calendar


BEIJING = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")

BLS_RELEASES = (
    {
        "needle": "employment situation",
        "slug": "nfp",
        "title": "美国{month}非农就业报告",
        "category": "就业",
        "importance": 3,
        "why": "直接影响美联储就业判断和短端利率，是全球资产最重要的月度重定价窗口之一。",
        "watch": "新增就业、失业率、时薪、劳动参与率和前两月修订。",
        "assets": ["美债", "美元", "美股", "黄金"],
    },
    {
        "needle": "consumer price index",
        "slug": "cpi",
        "title": "美国{month}CPI",
        "category": "通胀",
        "importance": 3,
        "why": "最容易同时改变美债、美元和成长股定价的通胀数据。",
        "watch": "核心月率、住房与服务通胀、前值修订，而不只看同比。",
        "assets": ["美债", "美元", "美股", "黄金"],
    },
    {
        "needle": "producer price index",
        "slug": "ppi",
        "title": "美国{month}PPI",
        "category": "通胀",
        "importance": 2,
        "why": "为PCE通胀和企业利润率提供前瞻信息。",
        "watch": "核心服务、贸易服务和前值修订。",
        "assets": ["美债", "美元", "美股"],
    },
)


@dataclass(frozen=True)
class CalendarSyncResult:
    fetched: int
    matched: int
    replaced: int
    total: int
    as_of: str


def sync_economic_calendar(config: dict, *, now: datetime | None = None) -> CalendarSyncResult:
    calendar_config = config.get("calendar", {})
    path = Path(calendar_config.get("path", "ui/economic-calendar.json"))
    source_url = calendar_config.get(
        "bls_ics_url",
        "https://www.bls.gov/schedule/news_release/bls.ics",
    )
    schedule_url = calendar_config.get(
        "bls_schedule_url",
        f"https://www.bls.gov/schedule/{current_year(now)}/home.htm",
    )
    horizon_days = max(30, min(730, int(calendar_config.get("horizon_days", 370))))
    current = (now or datetime.now(BEIJING)).astimezone(BEIJING)

    with httpx.Client(timeout=30, follow_redirects=True, headers=_request_headers()) as client:
        fetched, replacements, provider = _fetch_bls_events(
            client,
            source_url,
            schedule_url,
            current,
            current + timedelta(days=horizon_days),
        )

    lock = FileLock(str(path) + ".lock", timeout=10)
    with lock:
        payload = json.loads(path.read_text(encoding="utf-8"))
        old_events = payload.get("events", [])
        replaceable = {
            event["id"]
            for event in old_events
            if event.get("source_id") == "bls"
            and event.get("category") in {"就业", "通胀"}
            and event.get("starts_at", "")[:10] >= current.date().isoformat()
        }
        kept = [event for event in old_events if event.get("id") not in replaceable]
        events = sorted([*kept, *replacements], key=lambda event: event["starts_at"])
        payload["events"] = events
        payload["as_of"] = current.isoformat()
        payload["sync"] = {
            "last_success_at": current.isoformat(),
            "provider": provider,
            "provider_url": source_url if provider.endswith("iCalendar") else schedule_url,
            "matched_events": len(replacements),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    return CalendarSyncResult(
        fetched=fetched,
        matched=len(replacements),
        replaced=len(replaceable),
        total=len(events),
        as_of=current.isoformat(),
    )


def _fetch_bls_events(
    client: httpx.Client,
    ics_url: str,
    schedule_url: str,
    start: datetime,
    end: datetime,
) -> tuple[int, list[dict], str]:
    ics_error: Exception | None = None
    try:
        response = client.get(ics_url, headers={"Accept": "text/calendar,text/plain;q=0.9,*/*;q=0.1"})
        response.raise_for_status()
        parsed = Calendar.from_ical(response.content)
        components = [item for item in parsed.walk() if item.name == "VEVENT"]
        events = _bls_events(components, start, end)
        if not events:
            raise ValueError("BLS ICS contained no matching future releases")
        return len(components), events, "BLS official iCalendar"
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        ics_error = exc

    try:
        response = client.get(schedule_url, headers={"Accept": "text/html,application/xhtml+xml"})
        response.raise_for_status()
        rows = _schedule_rows(response.text)
        events = _bls_events_from_rows(rows, start, end)
        if not events:
            raise ValueError("BLS schedule page contained no matching future releases")
        return len(rows), events, "BLS official schedule page"
    except (httpx.HTTPError, ValueError) as page_error:
        raise RuntimeError(
            f"BLS official calendar unavailable (ICS: {ics_error}; HTML: {page_error})"
        ) from page_error


def _schedule_rows(html: str) -> list[tuple[datetime, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[tuple[datetime, str]] = []
    for row in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("th, td")]
        if len(cells) < 3 or not cells[1] or not cells[2]:
            continue
        try:
            starts_at = datetime.strptime(
                f"{cells[0]} {cells[1]}",
                "%A, %B %d, %Y %I:%M %p",
            ).replace(tzinfo=NEW_YORK)
        except ValueError:
            continue
        rows.append((starts_at, cells[2]))
    return rows


def _bls_events_from_rows(
    rows: list[tuple[datetime, str]],
    start: datetime,
    end: datetime,
) -> list[dict]:
    components = []
    for starts_at, summary in rows:
        component = _ScheduleComponent(starts_at, summary)
        components.append(component)
    return _bls_events(components, start, end)


class _ScheduleComponent:
    def __init__(self, starts_at: datetime, summary: str):
        self.starts_at = starts_at
        self.summary = summary

    def get(self, key: str, default=""):
        return self.summary if key.casefold() == "summary" else default

    def decoded(self, key: str):
        if key.casefold() != "dtstart":
            raise KeyError(key)
        return self.starts_at


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": "https://www.bls.gov/schedule/",
    }


def current_year(value: datetime | None = None) -> int:
    return (value or datetime.now(BEIJING)).astimezone(BEIJING).year


def _bls_events(components: list, start: datetime, end: datetime) -> list[dict]:
    events: dict[str, dict] = {}
    for component in components:
        summary = str(component.get("summary", "")).strip()
        release = next(
            (item for item in BLS_RELEASES if item["needle"] in summary.casefold()),
            None,
        )
        if release is None:
            continue
        starts_at = _component_start(component)
        if starts_at < start or starts_at > end:
            continue
        month = _previous_month(starts_at.date())
        identifier = f"{starts_at.date().isoformat()}-us-{release['slug']}"
        events[identifier] = {
            "id": identifier,
            "starts_at": starts_at.astimezone(BEIJING).isoformat(),
            "region": "美国",
            "country": "美国",
            "title": release["title"].format(month=f"{month.month}月"),
            "category": release["category"],
            "importance": release["importance"],
            "why": release["why"],
            "watch": release["watch"],
            "assets": release["assets"],
            "source_id": "bls",
        }
    return sorted(events.values(), key=lambda event: event["starts_at"])


def _component_start(component) -> datetime:
    value = component.decoded("dtstart")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=NEW_YORK)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(8, 30), tzinfo=NEW_YORK)
    raise ValueError(f"Unsupported DTSTART: {value!r}")


def _previous_month(value: date) -> date:
    return (value.replace(day=1) - timedelta(days=1)).replace(day=1)
