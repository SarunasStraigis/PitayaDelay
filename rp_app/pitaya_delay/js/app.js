const API = "/pitaya_delay/api";
const CONTROL = "/pitaya_delay/control";
const HIST_N = 80;

const statusEl = document.getElementById("status");
const delayEl = document.getElementById("delay");
const subEl = document.getElementById("sub");
const detailEl = document.getElementById("detail");
const statsEl = document.getElementById("stats");
const errEl = document.getElementById("err");
const canvas = document.getElementById("trace");
const btnStart = document.getElementById("btnStart");
const btnStop = document.getElementById("btnStop");

const hist = [];
let pinsReady = false;
let busy = false;

function fmt(v, digits, empty) {
  if (v === null || v === undefined || v === "") return empty || "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const text = n.toFixed(digits);
  return n > 0 ? "+" + text : text;
}

function plain(v, digits) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toFixed(digits);
}

async function getJson(url) {
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw new Error(resp.status + " " + url);
  return resp.json();
}

async function sendJson(url, method, body) {
  const resp = await fetch(url, {
    method: method,
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  const data = await resp.json().catch(function () { return {}; });
  if (!resp.ok) throw new Error(data.error || (resp.status + " " + url));
  return data;
}

function parseHz(text) {
  return Number(String(text).trim().replace(/,/g, ""));
}

function fillConfig(cfg) {
  if (!cfg) return;
  if (cfg.mode) document.getElementById("mode").value = cfg.mode;
  if (cfg.f_osc !== undefined && cfg.f_osc !== null) document.getElementById("f_osc").value = String(cfg.f_osc);
  if (cfg.harmonic !== undefined && cfg.harmonic !== null) document.getElementById("harmonic").value = String(cfg.harmonic);
  if (cfg.demod_hz !== undefined && cfg.demod_hz !== null) document.getElementById("demod").value = String(cfg.demod_hz);
  if (cfg.volt !== undefined && cfg.volt !== null) document.getElementById("volt").value = String(cfg.volt);
  if (cfg.out_ch !== undefined && cfg.out_ch !== null) document.getElementById("out_ch").value = String(cfg.out_ch);
  document.getElementById("gen_enable").checked = !!cfg.gen_enable;
  document.getElementById("use_fft").checked = cfg.use_fft !== false;
}

function fillPins(payload) {
  const pins = payload.pins || [];
  const start = document.getElementById("startPin");
  const stop = document.getElementById("stopPin");
  pinsReady = false;
  start.innerHTML = "";
  stop.innerHTML = "";
  pins.forEach(function (pin) {
    const label = pin.label || pin.name;
    start.add(new Option(label, String(pin.index)));
    stop.add(new Option(label, String(pin.index)));
  });
  if (payload.start) start.value = String(payload.start.index);
  if (payload.stop) stop.value = String(payload.stop.index);
  const selectable = payload.selectable !== false;
  start.disabled = !selectable;
  stop.disabled = !selectable;
  pinsReady = true;
}

function showSnap(snap) {
  const delay = snap.delay_ps;
  delayEl.textContent = delay === null || delay === undefined ? "—" : fmt(delay, 3) + " ps";
  subEl.textContent = "mode " + (snap.mode || "—")
    + "    DMTD " + fmt(snap.dmtd_ps, 3) + " ps   " + fmt(snap.dmtd_deg, 3) + " deg"
    + "    TDC " + fmt(snap.tdc_ps, 3) + " ps";
  const slip = snap.unwrap_slip === true ? "YES" : snap.unwrap_slip === false ? "no" : "—";
  detailEl.textContent = "nco " + plain(snap.beat_hz, 2) + " Hz"
    + "    magA " + plain(snap.mag_a, 4) + "  magB " + plain(snap.mag_b, 4)
    + "    rmsA " + plain(snap.rms_a, 4) + "  rmsB " + plain(snap.rms_b, 4)
    + "    slip " + slip;
  if (hist.length >= 2) {
    const mean = hist.reduce(function (a, b) { return a + b; }, 0) / hist.length;
    const variance = hist.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / (hist.length - 1);
    statsEl.textContent = "last " + hist.length + ":  mean " + fmt(mean, 3) + " ps   rms " + Math.sqrt(variance).toFixed(3) + " ps";
  } else {
    statsEl.textContent = "";
  }
  const bits = [];
  if (!snap.valid) bits.push("valid=false");
  if (snap.dmtd_error) bits.push(String(snap.dmtd_error));
  errEl.textContent = bits.join("   ");
}

function draw() {
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth;
  const h = canvas.height = 120;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#333";
  ctx.beginPath();
  ctx.moveTo(0, h / 2);
  ctx.lineTo(w, h / 2);
  ctx.stroke();
  if (hist.length < 2) return;
  const lo = Math.min.apply(null, hist);
  const hi = Math.max.apply(null, hist);
  const span = Math.max(hi - lo, 1e-6);
  ctx.strokeStyle = "#6dbe7a";
  ctx.lineWidth = 2;
  ctx.beginPath();
  hist.forEach(function (v, i) {
    const x = i * (w - 2) / (hist.length - 1);
    const y = h - 4 - (v - lo) / span * (h - 8);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

async function poll() {
  try {
    const health = await getJson(API + "/health");
    const snap = await getJson(API + "/latest");
    const scpi = snap.dmtd_error ? "down" : "up";
    statusEl.textContent = "v" + (health.version || "?")
      + "  ok=" + health.ok
      + "  FPGA " + health.id
      + "  mode=" + (health.mode || snap.mode)
      + "  SCPI " + scpi;
    if (snap.valid && snap.delay_ps !== null && snap.delay_ps !== undefined && !snap.dmtd_error) {
      hist.push(Number(snap.delay_ps));
      if (hist.length > HIST_N) hist.shift();
    }
    showSnap(snap);
  } catch (err) {
    if (busy) return;
    const msg = String(err.message || err);
    if (msg.indexOf("502") !== -1) {
      statusEl.textContent = "Stopped — the measurement server is not running";
      errEl.textContent = "502 from the menu proxy. Press Start to load the overlay.";
      return;
    }
    statusEl.textContent = "Stopped — Start to load Pitaya Delay";
    errEl.textContent = msg;
  }
  draw();
}

async function loadConfig() {
  try {
    fillConfig(await getJson(API + "/config"));
  } catch (err) {
    statusEl.textContent = "Config load failed: " + (err.message || err);
  }
}

async function loadPins() {
  try {
    fillPins(await getJson(API + "/pins"));
  } catch (err) {
    /* pins appear after Start */
  }
}

document.getElementById("btnApply").onclick = async function () {
  if (busy) return;
  let body;
  try {
    body = {
      mode: document.getElementById("mode").value,
      f_osc: parseHz(document.getElementById("f_osc").value),
      harmonic: parseInt(document.getElementById("harmonic").value, 10),
      demod_hz: parseHz(document.getElementById("demod").value),
      out_ch: parseInt(document.getElementById("out_ch").value, 10),
      volt: Number(document.getElementById("volt").value),
      gen_enable: document.getElementById("gen_enable").checked,
      use_fft: document.getElementById("use_fft").checked,
    };
    if (!Number.isFinite(body.f_osc) || !Number.isFinite(body.harmonic) || !Number.isFinite(body.demod_hz) || !Number.isFinite(body.volt)) {
      throw new Error("f_osc, N, demod, and Vpk must be numbers");
    }
  } catch (err) {
    statusEl.textContent = "Config: " + (err.message || err);
    return;
  }
  busy = true;
  statusEl.textContent = "Applying…";
  try {
    const cfg = await sendJson(API + "/config", "PUT", body);
    hist.length = 0;
    fillConfig(cfg);
    const lo = cfg.lo_hz ? (cfg.lo_hz / 1e6).toFixed(6) : "?";
    statusEl.textContent = "Config applied. LO " + lo + " MHz";
  } catch (err) {
    statusEl.textContent = "Apply failed: " + (err.message || err);
  } finally {
    busy = false;
  }
};

document.getElementById("btnZero").onclick = async function () {
  try {
    await sendJson(API + "/config", "PUT", { zero: true });
    hist.length = 0;
    statusEl.textContent = "Zero armed — next healthy DMTD burst becomes 0 ps";
  } catch (err) {
    statusEl.textContent = "Zero failed: " + (err.message || err);
  }
};

async function pushPins() {
  if (!pinsReady) return;
  try {
    const payload = await sendJson(API + "/pins", "PUT", {
      start: Number(document.getElementById("startPin").value),
      stop: Number(document.getElementById("stopPin").value),
    });
    fillPins(payload);
  } catch (err) {
    statusEl.textContent = "Pins failed: " + (err.message || err);
  }
}

document.getElementById("startPin").onchange = pushPins;
document.getElementById("stopPin").onchange = pushPins;

async function control(action) {
  if (busy) return;
  busy = true;
  btnStart.disabled = true;
  btnStop.disabled = true;
  statusEl.textContent = action === "start" ? "Starting…" : "Stopping…";
  errEl.textContent = "";
  try {
    const data = await sendJson(CONTROL + "/" + action, "POST", {});
    if (data.ok === false) throw new Error(data.error || data.log || "control failed");
    if (action === "start") {
      await loadConfig();
      await loadPins();
    }
    await poll();
  } catch (err) {
    const msg = String(err.message || err);
    if (msg.indexOf("502") !== -1) {
      statusEl.textContent = "Start failed: nothing is listening for Start (502)";
    } else {
      statusEl.textContent = action + " failed: " + msg;
    }
  } finally {
    busy = false;
    btnStart.disabled = false;
    btnStop.disabled = false;
  }
}

btnStart.onclick = function () { control("start"); };
btnStop.onclick = function () { control("stop"); };

loadConfig();
loadPins();
poll();
setInterval(poll, 400);
