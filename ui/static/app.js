const state = {
  dashboard: null,
  calendar: null,
  runtimeStatus: null,
  filter: "全部",
  focusKeywords: [],
  calendarRegion: "全部",
  calendarCategory: "全部",
  calendarRange: 90,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const decimals = Math.abs(number) < 10 ? 4 : 2;
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals }).format(number);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return { text: "—", className: "" };
  const number = Number(value);
  if (!Number.isFinite(number)) return { text: "—", className: "" };
  return { text: `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`, className: number >= 0 ? "positive" : "negative" };
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: "日期未知", time: "本地快照" };
  return {
    date: new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short" }).format(date),
    time: `${new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date)} CST`,
  };
}

function categoryFor(type = "") {
  if (/央行|宏观|数据|市场异动/.test(type)) return "宏观";
  if (/财政|产业|监管|政策/.test(type)) return "政策";
  if (/地缘|战争/.test(type)) return "地缘";
  if (/公司|财报|催化/.test(type)) return "公司";
  return "宏观";
}

async function loadDashboard(showFeedback = false) {
  const button = $("#refresh-button");
  button?.classList.add("loading");
  try {
    const [response, calendarResponse, statusResponse] = await Promise.all([
      fetch("/api/dashboard", { cache: "no-store" }),
      fetch("/api/calendar", { cache: "no-store" }).catch(() => null),
      fetch("/api/status", { cache: "no-store" }).catch(() => null),
    ]);
    if (!response.ok) throw new Error((await response.json()).detail || "数据载入失败");
    state.dashboard = await response.json();
    state.calendar = calendarResponse?.ok ? await calendarResponse.json() : null;
    state.runtimeStatus = statusResponse?.ok ? await statusResponse.json() : null;
    state.focusKeywords = [...(state.dashboard.settings?.focus_keywords || [])];
    renderDashboard();
    if (showFeedback) showToast("已重新载入本地快照");
  } catch (error) {
    renderLoadError(error.message);
    showToast(error.message);
  } finally {
    button?.classList.remove("loading");
  }
}

function renderDashboard() {
  const data = state.dashboard;
  const synthesis = data.synthesis || {};
  const stats = data.stats || {};
  const signals = data.signals || [];
  const date = formatDate(data.as_of);

  const schedulerHealthy = state.runtimeStatus?.scheduler_live;
  $("#as-of").textContent = `${date.time} · ${schedulerHealthy ? "调度正常" : "调度待检查"}`;
  $(".status-dot")?.classList.toggle("degraded", !schedulerHealthy);
  $("#brief-date").textContent = date.date;
  $("#demo-badge").hidden = !data.demo;
  $("#regime-title").textContent = synthesis.market_regime || "今日没有足够清晰的定价主线";
  $("#dominant-driver").textContent = synthesis.cross_asset_check || "等待更多价格验证，不为填满版面而制造结论。";
  $("#driver-detail").textContent = synthesis.dominant_driver || "暂无足够证据";
  $("#cross-asset").textContent = synthesis.cross_asset_check || "行情数据不足，暂不判断。";
  $("#political-economy").textContent = synthesis.political_economy || "今日无新增框架。";
  $("#signal-count").textContent = signals.length;
  $("#reading-time").textContent = Math.max(2, Math.min(5, Math.ceil((signals.length + (data.context || []).length) * 0.65)));
  $("#footer-status").textContent = data.demo
    ? "LOCAL · DEMO"
    : schedulerHealthy ? "SELF-HOSTED · HEALTHY" : "SELF-HOSTED · DEGRADED";

  renderMarket(data.market || [], data.market_error);
  renderFunnel(stats);
  renderSignals();
  renderQuestions(synthesis.calibration_questions || []);
  renderBlindSpots(synthesis.blind_spots || []);
  renderReviewLedger(data.reviews || [], data.review_summary || {});
  renderContext(data.context || []);
  renderCalendar();
  populateSettings(data.settings || {});
}

function calendarSourceMap() {
  return new Map((state.calendar?.sources || []).map((source) => [source.id, source]));
}

function calendarDayKey(value) {
  return String(value || "").slice(0, 10);
}

function shanghaiTodayKey() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function calendarDateParts(event) {
  const date = new Date(event.starts_at);
  const options = { timeZone: "Asia/Shanghai", month: "long", day: "numeric", weekday: "short" };
  return {
    date: new Intl.DateTimeFormat("zh-CN", options).format(date),
    time: event.time_tbd
      ? "时间待定"
      : new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false,
        }).format(date),
  };
}

function calendarCategoryMatches(event) {
  if (state.calendarCategory === "全部") return true;
  if (state.calendarCategory === "增长") return ["增长", "景气"].includes(event.category);
  return event.category === state.calendarCategory;
}

function filteredCalendarEvents() {
  const now = new Date();
  const todayKey = shanghaiTodayKey();
  const rangeEnd = new Date(now.getTime() + state.calendarRange * 86400000);
  return [...(state.calendar?.events || [])]
    .filter((event) => {
      const start = new Date(event.starts_at);
      const upcoming = event.time_tbd ? calendarDayKey(event.starts_at) >= todayKey : start >= now;
      const inRange = start <= rangeEnd;
      const inRegion = state.calendarRegion === "全部" || event.region === state.calendarRegion;
      return upcoming && inRange && inRegion && calendarCategoryMatches(event);
    })
    .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
}

function importanceLabel(level) {
  return Number(level) === 3 ? "一级事件" : "二级事件";
}

function calendarEventTemplate(event, sources) {
  const when = calendarDateParts(event);
  const source = sources.get(event.source_id) || {};
  const assets = (event.assets || []).map((asset) => `<span class="calendar-asset">${escapeHTML(asset)}</span>`).join("");
  return `
    <article class="calendar-event level-${escapeHTML(event.importance)}">
      <div class="calendar-event-time"><strong>${escapeHTML(when.time)}</strong><span>北京时间</span></div>
      <div class="calendar-event-body">
        <div class="calendar-event-meta">
          <span class="calendar-importance"><i class="importance-dot level-${escapeHTML(event.importance === 3 ? "three" : "two")}"></i>${escapeHTML(importanceLabel(event.importance))}</span>
          <span>${escapeHTML(event.country)}</span><span>·</span><span>${escapeHTML(event.category)}</span>
        </div>
        <h3>${escapeHTML(event.title)}</h3>
        <div class="calendar-event-detail">
          <p><b>为什么重要</b>${escapeHTML(event.why)}</p>
          <p><b>观察重点</b>${escapeHTML(event.watch)}</p>
        </div>
        <div class="calendar-assets">${assets}</div>
      </div>
      <a class="calendar-source" href="${escapeHTML(source.url || "#")}" target="_blank" rel="noopener noreferrer" aria-label="查看 ${escapeHTML(source.name || "官方")} 日程">官方 ↗</a>
    </article>`;
}

function renderCalendar() {
  const next = $("#calendar-next");
  const list = $("#calendar-list");
  if (!next || !list) return;
  if (!state.calendar) {
    next.innerHTML = `<div class="calendar-loading">财经日历暂时无法载入。</div>`;
    list.innerHTML = "";
    return;
  }

  const asOf = new Date(state.calendar.as_of);
  $("#calendar-updated").textContent = `核对至 ${new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric",
  }).format(asOf)} · 北京时间`;

  const events = filteredCalendarEvents();
  const sources = calendarSourceMap();
  if (!events.length) {
    next.innerHTML = `<div class="calendar-loading">当前筛选范围内没有已确认的高影响事件。</div>`;
    list.innerHTML = "";
    return;
  }

  const first = events[0];
  const firstWhen = calendarDateParts(first);
  next.innerHTML = `
    <div class="calendar-next-label"><span>下一风险窗口</span><strong>${escapeHTML(firstWhen.date)} · ${escapeHTML(firstWhen.time)}</strong></div>
    <div class="calendar-next-main">
      <div><span>${escapeHTML(first.country)} · ${escapeHTML(importanceLabel(first.importance))}</span><h3>${escapeHTML(first.title)}</h3></div>
      <p>${escapeHTML(first.why)}</p>
    </div>`;

  const groups = new Map();
  for (const event of events) {
    const key = calendarDayKey(event.starts_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  list.innerHTML = [...groups.entries()].map(([, dayEvents]) => {
    const label = calendarDateParts(dayEvents[0]).date;
    return `<section class="calendar-day"><div class="calendar-day-label"><span>${escapeHTML(label)}</span><i></i></div><div class="calendar-day-events">${dayEvents.map((event) => calendarEventTemplate(event, sources)).join("")}</div></section>`;
  }).join("");
}

function renderMarket(moves, error) {
  const track = $("#market-track");
  if (!moves.length) {
    track.innerHTML = `<div class="empty-state" style="width:100%">${escapeHTML(error || "行情快照暂不可用")}</div>`;
    return;
  }
  track.innerHTML = moves.map((move) => {
    const change = formatPercent(move.change_1d);
    return `
      <div class="market-item">
        <div class="market-name"><span>${escapeHTML(move.name)}</span><span class="market-symbol">${escapeHTML(move.symbol)}</span></div>
        <div class="market-price"><strong>${formatNumber(move.last)}</strong><span class="market-change ${change.className}">${change.text}</span></div>
      </div>`;
  }).join("");
}

function renderFunnel(stats) {
  const values = [stats.total_collected ?? 0, stats.analyzed ?? 0, stats.displayed ?? 0];
  $("#funnel").innerHTML = `
    <div><strong>${escapeHTML(values[0])}</strong><span>采集</span></div><b>›</b>
    <div><strong>${escapeHTML(values[1])}</strong><span>分析</span></div><b>›</b>
    <div class="funnel-final"><strong>${escapeHTML(values[2])}</strong><span>必看</span></div>`;
  const removed = Math.max(0, Number(values[0]) - Number(values[1]));
  $("#funnel-caption").textContent = removed
    ? `${removed} 条在调用深度分析前已被排除，注意力只留给可能改变定价的信息。`
    : "每天只把有限注意力留给真正改变定价的信息。";
}

function renderSignals() {
  const list = $("#signal-list");
  const allSignals = state.dashboard?.signals || [];
  const signals = state.filter === "全部"
    ? allSignals
    : allSignals.filter((signal) => categoryFor(signal.event_type) === state.filter);

  if (!signals.length) {
    list.innerHTML = `<div class="empty-state">这个分类今天没有达到阅读门槛的信号。</div>`;
    return;
  }

  list.innerHTML = signals.map((signal, index) => signalTemplate(signal, index)).join("");
}

function signalTemplate(signal, index) {
  const assets = (signal.affected_assets || []).map((asset) => `<span class="asset-pill">${escapeHTML(asset)}</span>`).join("");
  const watches = (signal.watch_signals || []).map((item) => `<span class="watch-chip">${escapeHTML(item)}</span>`).join("");
  const type = signal.event_type || "其他";
  return `
    <article class="signal-card" data-signal-index="${index}">
      <div class="signal-main">
        <span class="signal-number">${String(index + 1).padStart(2, "0")}</span>
        <div>
          <div class="signal-type-row">
            <span class="type-pill">${escapeHTML(type)}</span>
            <span class="source-name">${escapeHTML(signal.source || "未知来源")}</span>
            <span class="horizon">${escapeHTML(signal.time_horizon || "期限不确定")}</span>
          </div>
          <h3 class="signal-title">${escapeHTML(signal.title)}</h3>
          <p class="signal-summary">${escapeHTML(signal.summary || "暂无摘要")}</p>
        </div>
        <div class="score-block"><strong>${Number(signal.ranking_score || 0).toFixed(1)}</strong><span>EDGE SCORE</span></div>
        <button class="expand-button" type="button" aria-label="展开信号详情" aria-expanded="false">＋</button>
      </div>
      <div class="signal-detail">
        <div class="asset-row">${assets || '<span class="asset-pill">影响资产不明确</span>'}</div>
        <div class="detail-grid">
          <div class="detail-item"><h4>传导链</h4><p>${escapeHTML(signal.trading_logic || signal.asset_impact || "暂无")}</p></div>
          <div class="detail-item"><h4>已定价 / 预期差</h4><p>${escapeHTML(signal.priced_in || "不确定")}</p></div>
          <div class="detail-item"><h4>资产映射</h4><p>${escapeHTML(signal.asset_impact || "方向不确定")}</p></div>
          <div class="detail-item counter"><h4>反方审查</h4><p>${escapeHTML(signal.counter_argument || signal.consensus_gap || "暂无独立反方论证")}</p></div>
          <div class="detail-item invalidation"><h4>失效条件</h4><p>${escapeHTML(signal.invalidation || "暂无明确条件")}</p></div>
          <div class="detail-item"><h4>复盘目标</h4><p>${escapeHTML(signal.review_metric || "人工复核")} · ${escapeHTML(directionLabel(signal.expected_direction))} · ${escapeHTML(signal.review_horizon_days || 3)} 天</p></div>
          <div class="watch-row"><span>盯盘变量</span>${watches || '<span class="watch-chip">暂无</span>'}</div>
        </div>
      </div>
    </article>`;
}

function directionLabel(value) {
  if (value === "up") return "预期上行";
  if (value === "down") return "预期下行";
  return "观察验证";
}

function outcomeLabel(value) {
  return ({
    pending: "待复盘",
    supported: "得到支持",
    contradicted: "已被证伪",
    inconclusive: "尚不明确",
    unavailable: "等待数据",
  })[value] || "待复盘";
}

function shortDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "日期未知";
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
}

function renderReviewLedger(records, summary) {
  const container = $("#ledger-list");
  const stats = [
    [summary.pending || 0, "待复盘"],
    [summary.supported || 0, "得到支持"],
    [summary.contradicted || 0, "已被证伪"],
    [summary.inconclusive || 0, "不明确"],
  ];
  $("#ledger-summary").innerHTML = stats.map(([value, label]) => `
    <div class="ledger-stat"><strong>${escapeHTML(value)}</strong><span>${escapeHTML(label)}</span></div>`).join("");

  if (!records.length) {
    container.innerHTML = `<div class="empty-state" style="grid-column:1/-1">下一次真实采集后，入选信号会自动进入观点账本。</div>`;
    return;
  }

  container.innerHTML = records.slice(0, 6).map((record) => {
    const outcome = record.outcome || "pending";
    const change = formatPercent(record.price_change_pct);
    const manual = record.manual_outcome || "";
    const actions = state.dashboard?.demo
      ? `<p class="ledger-demo-note">示例记录 · 真实采集后可人工标记结果</p>`
      : `<div class="ledger-actions" aria-label="人工复盘结论">
          <button type="button" data-review-id="${escapeHTML(record.id)}" data-outcome="supported" class="${manual === "supported" ? "active" : ""}">兑现</button>
          <button type="button" data-review-id="${escapeHTML(record.id)}" data-outcome="contradicted" class="${manual === "contradicted" ? "active" : ""}">证伪</button>
          <button type="button" data-review-id="${escapeHTML(record.id)}" data-outcome="inconclusive" class="${manual === "inconclusive" ? "active" : ""}">不明确</button>
        </div>`;
    return `
      <article class="ledger-card">
        <div class="ledger-card-head">
          <span class="ledger-date">${shortDate(record.created_at)} → ${shortDate(record.due_at)}</span>
          <span class="outcome-badge ${escapeHTML(outcome)}">${escapeHTML(outcomeLabel(outcome))}</span>
        </div>
        <h3>${escapeHTML(record.title)}</h3>
        <p class="ledger-thesis">${escapeHTML(record.counter_argument ? `反方：${record.counter_argument}` : record.thesis || "等待补充论证")}</p>
        <div class="ledger-metric">
          <span>复盘目标</span><strong>${escapeHTML(record.review_metric || record.review_symbol || "人工复核")}</strong>
          <span>预期方向</span><strong>${escapeHTML(directionLabel(record.expected_direction))}</strong>
          <span>到期变动</span><strong class="ledger-change ${change.className}">${escapeHTML(change.text)}</strong>
        </div>
        ${actions}
      </article>`;
  }).join("");
}

async function updateReview(reviewId, outcome) {
  const record = (state.dashboard?.reviews || []).find((item) => item.id === reviewId);
  const nextOutcome = record?.manual_outcome === outcome ? "pending" : outcome;
  try {
    const response = await fetch(`/api/reviews/${encodeURIComponent(reviewId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome: nextOutcome, note: record?.note || "" }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "复盘保存失败");
    await loadDashboard();
    showToast("复盘结论已写入本地观点账本");
  } catch (error) {
    showToast(error.message);
  }
}

function renderQuestions(questions) {
  const container = $("#question-list");
  if (!questions.length) {
    container.innerHTML = `<p class="review-intro">今天没有足够清晰的复盘问题。</p>`;
    updateCompletion();
    return;
  }
  container.innerHTML = questions.slice(0, 3).map((question, index) => {
    const key = reviewKey(question);
    const checked = localStorage.getItem(key) === "1";
    return `
      <label class="question-item">
        <input type="checkbox" data-review-key="${escapeHTML(key)}" ${checked ? "checked" : ""}>
        <span class="question-check">✓</span>
        <span>${escapeHTML(question)}</span>
      </label>`;
  }).join("");
  updateCompletion();
}

function reviewKey(question) {
  let hash = 0;
  for (const char of question) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  return `tidebrief-review-${hash}`;
}

function updateCompletion() {
  const inputs = $$("#question-list input[type='checkbox']");
  const done = inputs.filter((input) => input.checked).length;
  $("#completion-text").textContent = `${done} / ${inputs.length}`;
  $("#completion-bar").style.width = inputs.length ? `${(done / inputs.length) * 100}%` : "0%";
}

function renderBlindSpots(items) {
  $("#blind-spots").innerHTML = items.length
    ? items.slice(0, 3).map((item) => `<li>${escapeHTML(item)}</li>`).join("")
    : "<li>暂无明确证伪变量</li>";
}

function renderContext(items) {
  $("#context-grid").innerHTML = items.length
    ? items.slice(0, 2).map((item, index) => `
        <article class="context-card" data-index="${String(index + 1).padStart(2, "0")}">
          <div class="context-card-meta"><i></i><span>${escapeHTML(item.event_type || "背景框架")}</span><span>·</span><span>${escapeHTML(item.source || "")}</span></div>
          <h3>${escapeHTML(item.title)}</h3>
          <p>${escapeHTML(item.political_economy_lesson || item.summary || "暂无")}</p>
        </article>`).join("")
    : `<div class="empty-state">今日没有值得额外占用时间的背景阅读。</div>`;
}

function renderLoadError(message) {
  $("#regime-title").textContent = "本地快照暂时无法载入";
  $("#dominant-driver").textContent = message;
  $("#signal-list").innerHTML = `<div class="empty-state">${escapeHTML(message)}</div>`;
}

function populateSettings(settings) {
  state.focusKeywords = [...(settings.focus_keywords || [])];
  $("#daily-limit").value = settings.max_daily_items ?? 8;
  $("#context-limit").value = settings.max_context_items ?? 2;
  updateRangeOutputs();
  renderKeywordChips();
}

function renderKeywordChips() {
  $("#keyword-chips").innerHTML = state.focusKeywords.map((keyword, index) => `
    <span class="keyword-chip">${escapeHTML(keyword)}<button type="button" data-remove-keyword="${index}" aria-label="删除 ${escapeHTML(keyword)}">×</button></span>`).join("");
}

function addKeyword(value) {
  const keyword = value.trim().replace(/\s+/g, " ").slice(0, 40);
  if (!keyword) return;
  if (!state.focusKeywords.some((item) => item.toLocaleLowerCase() === keyword.toLocaleLowerCase())) {
    state.focusKeywords.push(keyword);
    renderKeywordChips();
  }
  $("#keyword-input").value = "";
}

function updateRangeOutputs() {
  $("#daily-limit-output").textContent = $("#daily-limit").value;
  $("#context-limit-output").textContent = $("#context-limit").value;
}

function openSettings() {
  populateSettings(state.dashboard?.settings || {});
  $("#modal-status").textContent = "";
  $("#settings-modal").hidden = false;
  document.body.style.overflow = "hidden";
  setTimeout(() => $("#keyword-input").focus(), 60);
}

function closeSettings() {
  $("#settings-modal").hidden = true;
  document.body.style.overflow = "";
}

async function saveSettings(event) {
  event.preventDefault();
  const daily = Number($("#daily-limit").value);
  const context = Number($("#context-limit").value);
  if (context >= daily) {
    $("#modal-status").textContent = "背景阅读数量必须小于每日总量。";
    return;
  }

  const submit = $("#settings-form button[type='submit']");
  submit.disabled = true;
  $("#modal-status").textContent = "";
  try {
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ focus_keywords: state.focusKeywords, max_daily_items: daily, max_context_items: context }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "保存失败");
    state.dashboard.settings = { ...state.dashboard.settings, ...result };
    closeSettings();
    showToast("关注设置已保存，将在下次采集时生效");
  } catch (error) {
    $("#modal-status").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", () => loadDashboard(true));
  $("#open-settings").addEventListener("click", openSettings);
  $("#close-settings").addEventListener("click", closeSettings);
  $("#cancel-settings").addEventListener("click", closeSettings);
  $("#settings-modal").addEventListener("click", (event) => { if (event.target.id === "settings-modal") closeSettings(); });
  $("#settings-form").addEventListener("submit", saveSettings);

  $("#keyword-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === "," || event.key === "，") {
      event.preventDefault();
      addKeyword(event.target.value);
    }
  });
  $("#keyword-input").addEventListener("blur", (event) => addKeyword(event.target.value));
  $("#keyword-chips").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-keyword]");
    if (!button) return;
    state.focusKeywords.splice(Number(button.dataset.removeKeyword), 1);
    renderKeywordChips();
  });
  $("#daily-limit").addEventListener("input", updateRangeOutputs);
  $("#context-limit").addEventListener("input", updateRangeOutputs);

  $("#filter-row").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.filter = button.dataset.filter;
    $$(".filter-chip").forEach((item) => item.classList.toggle("active", item === button));
    renderSignals();
  });

  $("#calendar-region-filter").addEventListener("click", (event) => {
    const button = event.target.closest("[data-calendar-region]");
    if (!button) return;
    state.calendarRegion = button.dataset.calendarRegion;
    $$("#calendar-region-filter .calendar-chip").forEach((item) => item.classList.toggle("active", item === button));
    renderCalendar();
  });

  $("#calendar-category-filter").addEventListener("click", (event) => {
    const button = event.target.closest("[data-calendar-category]");
    if (!button) return;
    state.calendarCategory = button.dataset.calendarCategory;
    $$("#calendar-category-filter .calendar-chip").forEach((item) => item.classList.toggle("active", item === button));
    renderCalendar();
  });

  $("#calendar-range-filter").addEventListener("click", (event) => {
    const button = event.target.closest("[data-calendar-range]");
    if (!button) return;
    state.calendarRange = Number(button.dataset.calendarRange);
    $$("#calendar-range-filter .calendar-chip").forEach((item) => item.classList.toggle("active", item === button));
    renderCalendar();
  });

  $("#signal-list").addEventListener("click", (event) => {
    const button = event.target.closest(".expand-button");
    if (!button) return;
    const card = button.closest(".signal-card");
    const isOpen = card.classList.toggle("open");
    button.setAttribute("aria-expanded", String(isOpen));
    button.setAttribute("aria-label", isOpen ? "收起信号详情" : "展开信号详情");
  });

  $("#question-list").addEventListener("change", (event) => {
    const input = event.target.closest("input[data-review-key]");
    if (!input) return;
    localStorage.setItem(input.dataset.reviewKey, input.checked ? "1" : "0");
    updateCompletion();
  });

  $("#ledger-list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-review-id]");
    if (!button) return;
    updateReview(button.dataset.reviewId, button.dataset.outcome);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#settings-modal").hidden) closeSettings();
  });

  const sections = ["today", "calendar", "signals", "review", "ledger"].map((id) => document.getElementById(id));
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    $$(".nav-link").forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${visible.target.id}`));
  }, { rootMargin: "-20% 0px -70%", threshold: [0, .2, .5] });
  sections.forEach((section) => section && observer.observe(section));
}

bindEvents();
loadDashboard();
