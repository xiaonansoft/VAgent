const CRITICAL_TEMP_C = 1361.0;

const els = {
  healthPill: document.getElementById("healthPill"),
  streamPill: document.getElementById("streamPill"),
  ironTemp: document.getElementById("ironTemp"),
  siContent: document.getElementById("siContent"),
  isOneCan: document.getElementById("isOneCan"),
  useLiveTempBtn: document.getElementById("useLiveTempBtn"),
  liveTempHint: document.getElementById("liveTempHint"),
  chatMessage: document.getElementById("chatMessage"),
  chatLog: document.getElementById("chatLog"),
  sendBtn: document.getElementById("sendBtn"),
  monitorHint: document.getElementById("monitorHint"),
  kpiTemp: document.getElementById("kpiTemp"),
  kpiCritical: document.getElementById("kpiCritical"),
  kpiMargin: document.getElementById("kpiMargin"),
  alertBox: document.getElementById("alertBox"),
  chart: document.getElementById("chart"),
  toolSelect: document.getElementById("toolSelect"),
  refreshToolsBtn: document.getElementById("refreshToolsBtn"),
  callToolBtn: document.getElementById("callToolBtn"),
  toolArgs: document.getElementById("toolArgs"),
  toolOutput: document.getElementById("toolOutput"),
};

els.kpiCritical.textContent = `${CRITICAL_TEMP_C.toFixed(1)}℃`;

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  els.chatLog.appendChild(div);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function parseNumber(value) {
  const v = Number(value);
  return Number.isFinite(v) ? v : null;
}

function setPill(pillEl, level, text) {
  pillEl.classList.remove("muted", "ok", "warn", "danger");
  pillEl.classList.add(level);
  pillEl.textContent = text;
}

function setCode(el, value) {
  if (typeof value === "string") {
    el.textContent = value;
    return;
  }
  el.textContent = JSON.stringify(value, null, 2);
}

function setTextareaJson(textareaEl, value) {
  textareaEl.value = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function sendChat() {
  const message = (els.chatMessage.value || "").trim();
  if (!message) return;

  const ironTemp = parseNumber(els.ironTemp.value);
  const si = parseNumber(els.siContent.value);
  const isOneCan = !!els.isOneCan.checked;

  addMsg("user", message);
  els.chatMessage.value = "";
  els.sendBtn.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        message,
        iron_temp_c: ironTemp,
        si_content_pct: si,
        is_one_can: ironTemp !== null && si !== null ? isOneCan : null,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      addMsg("meta", `请求失败：${res.status} ${text}`);
      return;
    }

    const data = await res.json();
    addMsg("bot", data.reply || "");
    if (Array.isArray(data.tool_calls) && data.tool_calls.length) {
      addMsg("meta", `工具调用：\n${data.tool_calls.map((t) => `${t.name} ${JSON.stringify(t.arguments)}`).join("\n")}`);
    }
  } catch (e) {
    addMsg("meta", `请求异常：${String(e)}`);
  } finally {
    els.sendBtn.disabled = false;
  }
}

els.sendBtn.addEventListener("click", sendChat);
els.chatMessage.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    sendChat();
  }
});

document.querySelectorAll(".chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    const p = btn.getAttribute("data-prompt") || "";
    els.chatMessage.value = p;
    els.chatMessage.focus();
  });
});

const chart = echarts.init(els.chart);
const seriesTemp = [];
const seriesCritical = [];

function updateChart(ts, tempC) {
  seriesTemp.push([ts, tempC]);
  seriesCritical.push([ts, CRITICAL_TEMP_C]);

  while (seriesTemp.length > 240) {
    seriesTemp.shift();
    seriesCritical.shift();
  }

  chart.setOption(
    {
      animation: false,
      tooltip: { trigger: "axis" },
      legend: { data: ["温度", "临界温度"] },
      xAxis: { type: "time" },
      yAxis: { type: "value", name: "℃" },
      series: [
        { name: "温度", type: "line", showSymbol: false, data: seriesTemp, lineStyle: { width: 2 } },
        { name: "临界温度", type: "line", showSymbol: false, data: seriesCritical, lineStyle: { type: "dashed" } },
      ],
    },
    { notMerge: true }
  );
}

function setAlert(level, text) {
  els.alertBox.classList.remove("muted", "warn", "danger");
  els.alertBox.classList.add(level);
  els.alertBox.textContent = text;
}

let lastTemp = null;
let lastTs = null;

function updateKpis(tempC) {
  els.kpiTemp.textContent = `${tempC.toFixed(1)}℃`;
  const margin = tempC - CRITICAL_TEMP_C;
  els.kpiMargin.textContent = `${margin.toFixed(1)}℃`;

  if (margin >= 0) {
    setAlert("danger", "已接近/突破临界温度：建议立即压温（生铁块/氧化铁皮），保持低枪位搅拌，严禁提枪。");
  } else if (margin > -3) {
    setAlert("warn", "临界温度附近：建议提前准备压温物料，避免温度越线。");
  } else {
    setAlert("muted", "暂无告警");
  }
}

function startStream() {
  const es = new EventSource("/api/stream");
  setPill(els.streamPill, "warn", "数据流：连接中");
  es.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data);
      const t = payload?.temperature?.value;
      const ts = payload?.temperature?.ts;
      if (typeof t === "number" && ts) {
        lastTemp = t;
        lastTs = ts;
        els.liveTempHint.textContent = `当前：${t.toFixed(1)}℃`;
        els.monitorHint.textContent = `最近更新：${new Date(ts).toLocaleTimeString()}`;
        setPill(els.streamPill, "ok", "数据流：已连接");
        updateKpis(t);
        updateChart(new Date(ts), t);
      }
    } catch (e) {
      addMsg("meta", `数据流解析失败：${String(e)}`);
    }
  };
  es.onerror = () => {
    setPill(els.streamPill, "warn", "数据流：重连中");
    setAlert("warn", "数据流中断，正在尝试重连…");
  };
}

window.addEventListener("resize", () => chart.resize());
startStream();
addMsg("meta", "提示：按 Ctrl/⌘ + Enter 发送；右侧为实时温度与告警（模拟数据）。");

els.useLiveTempBtn.addEventListener("click", () => {
  if (typeof lastTemp === "number") {
    els.ironTemp.value = String(lastTemp.toFixed(1));
  }
});

async function pollHealth() {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    if (!res.ok) {
      setPill(els.healthPill, "warn", `后端：${res.status}`);
      return;
    }
    const data = await res.json();
    if (data && data.ok === true) {
      setPill(els.healthPill, "ok", "后端：OK");
    } else {
      setPill(els.healthPill, "warn", "后端：异常");
    }
  } catch (e) {
    setPill(els.healthPill, "danger", "后端：不可达");
  }
}

const defaultArgsByTool = {
  calculate_thermal_balance: { iron_temp_c: 1340, si_content_pct: 0.28, is_one_can: true },
  recommend_lance_profile: { si_content_pct: 0.28 },
  predict_critical_temp: { current_temp_c: 1358, v_content_pct: 0.12 },
  diagnose_low_yield: { slag: { V2O5: 1.0, SiO2: 1.0, TiO2: 1.0, CaO: 45.0 }, process: { tap_time_min: 3.0, coolant_type_used: "弃渣球", coolant_structure_notes: ["批次A"] } },
};

function setArgsTemplate(toolName) {
  const template = defaultArgsByTool[toolName] || {};
  setTextareaJson(els.toolArgs, template);
}

async function refreshTools() {
  els.refreshToolsBtn.disabled = true;
  try {
    const res = await fetch("/mcp/tools", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
    });
    const data = await res.json();
    const tools = data?.result?.tools || [];
    els.toolSelect.innerHTML = "";
    tools.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.name;
      opt.textContent = `${t.name}｜${t.description || ""}`;
      els.toolSelect.appendChild(opt);
    });
    if (tools.length) {
      setArgsTemplate(tools[0].name);
      setCode(els.toolOutput, { tools: tools.map((t) => ({ name: t.name, description: t.description })) });
    } else {
      setCode(els.toolOutput, { error: "tools/list 返回为空" });
    }
  } catch (e) {
    setCode(els.toolOutput, { error: String(e) });
  } finally {
    els.refreshToolsBtn.disabled = false;
  }
}

async function callTool() {
  const toolName = els.toolSelect.value;
  let args = {};
  try {
    args = JSON.parse(els.toolArgs.value || "{}");
  } catch (e) {
    setCode(els.toolOutput, { error: "arguments 不是合法 JSON", detail: String(e) });
    return;
  }

  els.callToolBtn.disabled = true;
  try {
    const res = await fetch("/mcp/tools", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: Date.now(),
        method: "tools/call",
        params: { name: toolName, arguments: args },
      }),
    });
    const data = await res.json();
    setCode(els.toolOutput, data);
  } catch (e) {
    setCode(els.toolOutput, { error: String(e) });
  } finally {
    els.callToolBtn.disabled = false;
  }
}

els.refreshToolsBtn.addEventListener("click", refreshTools);
els.callToolBtn.addEventListener("click", callTool);
els.toolSelect.addEventListener("change", () => setArgsTemplate(els.toolSelect.value));

pollHealth();
setInterval(pollHealth, 10000);
refreshTools();
