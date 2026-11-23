// TAPTEMPO.EXE: tap tempo, metronome, and setlist count-ins.
// Reads (never writes) the Setlister library stored in this browser.
import example from "../data/setlister-example-library.json";

const SETLISTER_STORE = "setlister-library-v1";
const PREFS_STORE = "taptempo-prefs-v1";
const MIN_BPM = 20;
const MAX_BPM = 300;

const $ = (id) => document.getElementById(id);
const clampBpm = (v) =>
  Math.min(MAX_BPM, Math.max(MIN_BPM, Math.round(Number(v) || 120)));

// ---------- preferences ----------
function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_STORE)) || {};
  } catch {
    return {};
  }
}
function savePrefs() {
  try {
    localStorage.setItem(
      PREFS_STORE,
      JSON.stringify({
        bpm: metro.bpm,
        beats: metro.beats,
        sub: metro.sub,
        volume: metro.volume,
        accent: metro.accent,
        countBars: Number($("countBars").value),
        setlistId: set.activeId,
      }),
    );
  } catch {
    /* storage unavailable: ignore */
  }
}

// ---------- metronome (Web Audio lookahead scheduler) ----------
const metro = {
  bpm: 120,
  beats: 4,
  sub: 1,
  volume: 0.7,
  accent: true,
  running: false,
  countTicksLeft: null, // number while a count-in is playing
  ctx: null,
  nextTime: 0,
  tick: 0,
  timer: null,
  queue: [], // {time, beatIndex, isBeat}
  run: 0, // increments on every start/stop so stale timeouts can't stop a newer run
};

const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD_S = 0.12;

function audio() {
  if (!metro.ctx)
    metro.ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (metro.ctx.state === "suspended") metro.ctx.resume();
  return metro.ctx;
}

function click(time, kind) {
  const ctx = metro.ctx;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const freq = { accent: 1760, beat: 1175, sub: 784 }[kind];
  const level = { accent: 1, beat: 0.75, sub: 0.4 }[kind] * metro.volume;
  osc.type = "square";
  osc.frequency.setValueAtTime(freq, time);
  gain.gain.setValueAtTime(0.0001, time);
  gain.gain.exponentialRampToValueAtTime(Math.max(level, 0.0002), time + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.045);
  osc.connect(gain).connect(ctx.destination);
  osc.start(time);
  osc.stop(time + 0.06);
}

function scheduler() {
  const ctx = metro.ctx;
  while (metro.nextTime < ctx.currentTime + SCHEDULE_AHEAD_S) {
    if (metro.countTicksLeft !== null && metro.countTicksLeft <= 0) {
      // Count-in finished: stop once the last click has sounded.
      const endAt = metro.nextTime;
      const run = metro.run;
      clearInterval(metro.timer);
      metro.timer = null;
      setTimeout(
        () => run === metro.run && stop(),
        Math.max(0, (endAt - ctx.currentTime) * 1000),
      );
      return;
    }
    const ticksPerBar = metro.beats * metro.sub;
    const inBar = metro.tick % ticksPerBar;
    const isBeat = inBar % metro.sub === 0;
    const beatIndex = Math.floor(inBar / metro.sub);
    const kind = !isBeat
      ? "sub"
      : beatIndex === 0 && metro.accent
        ? "accent"
        : "beat";
    click(metro.nextTime, kind);
    metro.queue.push({ time: metro.nextTime, beatIndex, isBeat });

    metro.nextTime += 60 / metro.bpm / metro.sub;
    metro.tick += 1;
    if (metro.countTicksLeft !== null) metro.countTicksLeft -= 1;
  }
}

function start({ countIn = false } = {}) {
  if (metro.running) stop();
  const ctx = audio();
  metro.run += 1;
  metro.running = true;
  metro.tick = 0;
  metro.queue = [];
  metro.nextTime = ctx.currentTime + 0.06;
  metro.countTicksLeft = countIn
    ? Number($("countBars").value) * metro.beats * metro.sub
    : null;
  metro.timer = setInterval(scheduler, LOOKAHEAD_MS);
  scheduler();
  renderTransport();
  requestAnimationFrame(drawLights);
}

function stop() {
  metro.run += 1;
  clearInterval(metro.timer);
  metro.timer = null;
  metro.running = false;
  metro.countTicksLeft = null;
  metro.queue = [];
  renderTransport();
  lightBeat(-1);
}

function renderTransport() {
  const counting = metro.running && metro.countTicksLeft !== null;
  const ss = $("startStop");
  ss.textContent = metro.running && !counting ? "■ Stop" : "▶ Start";
  ss.classList.toggle("running", metro.running && !counting);
  const ci = $("countIn");
  ci.textContent = counting ? "■ Stop" : "Count in";
  ci.classList.toggle("running", counting);
  $("beatLights").classList.toggle("counting", counting);
}

function buildLights() {
  const box = $("beatLights");
  box.innerHTML = "";
  for (let i = 0; i < metro.beats; i++)
    box.appendChild(document.createElement("i"));
}

function lightBeat(index) {
  [...$("beatLights").children].forEach((el, i) => {
    el.classList.toggle("on", i === index);
    el.classList.toggle("accent", i === 0 && metro.accent);
  });
}

function drawLights() {
  if (!metro.running || !metro.ctx) return;
  const now = metro.ctx.currentTime;
  let last = null;
  while (metro.queue.length && metro.queue[0].time <= now)
    last = metro.queue.shift();
  if (last && last.isBeat) lightBeat(last.beatIndex);
  requestAnimationFrame(drawLights);
}

function setBpm(v, { fromSong = false } = {}) {
  metro.bpm = clampBpm(v);
  $("bpmInput").value = metro.bpm;
  $("bpmSlider").value = metro.bpm;
  if (!fromSong) $("songLabel").textContent = "";
  savePrefs();
}

// ---------- tap tempo ----------
const tap = { times: [], bpm: null };
const TAP_RESET_MS = 2000;
const TAP_WINDOW = 8;

function doTap() {
  const now = performance.now();
  if (tap.times.length && now - tap.times[tap.times.length - 1] > TAP_RESET_MS)
    tap.times = [];
  tap.times.push(now);
  if (tap.times.length > TAP_WINDOW + 1) tap.times.shift();

  const pad = $("tapPad");
  pad.classList.add("hit");
  setTimeout(() => pad.classList.remove("hit"), 80);

  if (tap.times.length < 2) {
    tap.bpm = null;
    $("tapBpm").textContent = "···";
    $("tapInfo").textContent = "keep tapping…";
    renderTapButtons();
    return;
  }
  const intervals = tap.times.slice(1).map((t, i) => t - tap.times[i]);
  const mean = intervals.reduce((a, b) => a + b, 0) / intervals.length;
  const sd = Math.sqrt(
    intervals.reduce((a, b) => a + (b - mean) ** 2, 0) / intervals.length,
  );
  tap.bpm = 60000 / mean;
  $("tapBpm").textContent = tap.bpm.toFixed(1);
  const steadiness =
    sd / mean < 0.03 ? "steady" : sd / mean < 0.08 ? "ok" : "wobbly";
  $("tapInfo").textContent = `${tap.times.length} taps · ${steadiness}`;
  renderTapButtons();
}

function resetTap() {
  tap.times = [];
  tap.bpm = null;
  $("tapBpm").textContent = "---";
  $("tapInfo").textContent = "tap here or press T";
  renderTapButtons();
}

function renderTapButtons() {
  const has = tap.bpm !== null;
  ["tapHalf", "tapDouble", "tapUse"].forEach((id) => ($(id).disabled = !has));
  $("tapHalfVal").textContent = has ? Math.round(tap.bpm / 2) : "";
  $("tapDoubleVal").textContent = has ? Math.round(tap.bpm * 2) : "";
}

// ---------- setlist (read-only view of Setlister's library) ----------
const set = { library: null, activeId: null, index: -1 };

function readLibrary() {
  try {
    const lib = JSON.parse(localStorage.getItem(SETLISTER_STORE));
    if (lib && Array.isArray(lib.songs) && Array.isArray(lib.setlists))
      return lib;
  } catch {
    /* fall through */
  }
  return null;
}

function activeSongs() {
  if (!set.library) return [];
  const byId = new Map(set.library.songs.map((s) => [String(s.id), s]));
  const list = set.library.setlists.find((s) => String(s.id) === set.activeId);
  return list
    ? (list.songIds || []).map((id) => byId.get(String(id))).filter(Boolean)
    : [];
}

function renderSetlist() {
  const select = $("setlistSelect");
  const lists = set.library ? set.library.setlists : [];
  select.innerHTML = "";
  lists.forEach((l) =>
    select.add(new Option(l.name || "Untitled Set", String(l.id))),
  );
  select.value = set.activeId ?? "";
  select.disabled = !lists.length;

  const songs = activeSongs();
  const ol = $("songList");
  ol.innerHTML = "";
  songs.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "track" + (i === set.index ? " current" : "");
    li.innerHTML = `<div class="track-number"></div><div class="track-info"><strong></strong><span></span></div><div class="track-meta"></div>`;
    li.querySelector(".track-number").textContent = String(i + 1).padStart(
      2,
      "0",
    );
    li.querySelector("strong").textContent = s.title || "Untitled";
    li.querySelector(".track-info span").textContent = [s.artist, s.key]
      .filter(Boolean)
      .join(" · ");
    li.querySelector(".track-meta").textContent = `${clampBpm(s.bpm)} BPM`;
    li.addEventListener("click", () => selectSong(i));
    ol.appendChild(li);
  });
  $("setEmpty").hidden = songs.length > 0;
  $("prevSong").disabled = $("nextSong").disabled = songs.length === 0;
}

function selectSong(i) {
  const songs = activeSongs();
  if (!songs.length) return;
  set.index = Math.max(0, Math.min(songs.length - 1, i));
  const song = songs[set.index];
  setBpm(song.bpm, { fromSong: true });
  $("songLabel").textContent = song.title || "";
  renderSetlist();
  $("songList").children[set.index]?.scrollIntoView({ block: "nearest" });
}

function useLibrary(lib, preferredId) {
  set.library = lib;
  const ids = lib ? lib.setlists.map((l) => String(l.id)) : [];
  set.activeId = ids.includes(preferredId)
    ? preferredId
    : ids.includes(String(lib?.activeSetlistId))
      ? String(lib.activeSetlistId)
      : (ids[0] ?? null);
  set.index = -1;
  renderSetlist();
}

// ---------- wiring ----------
function isTyping(e) {
  const t = e.target;
  return (
    (t instanceof HTMLInputElement &&
      !["range", "checkbox"].includes(t.type)) ||
    t instanceof HTMLSelectElement ||
    t instanceof HTMLTextAreaElement
  );
}

function init() {
  const prefs = loadPrefs();
  metro.beats = Number(prefs.beats) || 4;
  metro.sub = Number(prefs.sub) || 1;
  metro.volume = prefs.volume ?? 0.7;
  metro.accent = prefs.accent ?? true;
  $("beatsSelect").value = metro.beats;
  $("subSelect").value = metro.sub;
  $("volume").value = metro.volume;
  $("accent").checked = metro.accent;
  if (prefs.countBars) $("countBars").value = prefs.countBars;
  buildLights();
  useLibrary(readLibrary(), prefs.setlistId);
  setBpm(prefs.bpm ?? 120);

  $("tapPad").addEventListener("pointerdown", (e) => {
    e.preventDefault();
    doTap();
  });
  $("tapReset").addEventListener("click", resetTap);
  $("tapHalf").addEventListener("click", () => setBpm(tap.bpm / 2));
  $("tapDouble").addEventListener("click", () => setBpm(tap.bpm * 2));
  $("tapUse").addEventListener("click", () => setBpm(tap.bpm));

  $("bpmDown").addEventListener("click", () => setBpm(metro.bpm - 1));
  $("bpmUp").addEventListener("click", () => setBpm(metro.bpm + 1));
  $("bpmInput").addEventListener("change", (e) => setBpm(e.target.value));
  $("bpmSlider").addEventListener("input", (e) => setBpm(e.target.value));

  $("beatsSelect").addEventListener("change", (e) => {
    metro.beats = Number(e.target.value);
    buildLights();
    savePrefs();
  });
  $("subSelect").addEventListener("change", (e) => {
    metro.sub = Number(e.target.value);
    savePrefs();
  });
  $("volume").addEventListener("input", (e) => {
    metro.volume = Number(e.target.value);
    savePrefs();
  });
  $("accent").addEventListener("change", (e) => {
    metro.accent = e.target.checked;
    savePrefs();
  });
  $("countBars").addEventListener("change", savePrefs);

  $("startStop").addEventListener("click", () =>
    metro.running && metro.countTicksLeft === null ? stop() : start(),
  );
  $("countIn").addEventListener("click", () =>
    metro.running && metro.countTicksLeft !== null
      ? stop()
      : start({ countIn: true }),
  );

  $("setlistSelect").addEventListener("change", (e) => {
    set.activeId = e.target.value;
    set.index = -1;
    renderSetlist();
    savePrefs();
  });
  $("prevSong").addEventListener("click", () => selectSong(set.index - 1));
  $("nextSong").addEventListener("click", () => selectSong(set.index + 1));
  $("loadExample").addEventListener("click", () => useLibrary(example));

  // Pick up changes made in Setlister in another tab.
  window.addEventListener("storage", (e) => {
    if (e.key === SETLISTER_STORE) useLibrary(readLibrary(), set.activeId);
  });

  document.addEventListener("keydown", (e) => {
    if (isTyping(e) || e.metaKey || e.ctrlKey || e.altKey) return;
    const step = e.shiftKey ? 5 : 1;
    switch (e.key.toLowerCase()) {
      case "t":
        doTap();
        break;
      case " ":
        e.preventDefault();
        $("startStop").click();
        break;
      case "c":
        $("countIn").click();
        break;
      case "arrowup":
        e.preventDefault();
        setBpm(metro.bpm + step);
        break;
      case "arrowdown":
        e.preventDefault();
        setBpm(metro.bpm - step);
        break;
      case "n":
        selectSong(set.index + 1);
        break;
      case "p":
        selectSong(set.index - 1);
        break;
      case "escape":
        stop();
        resetTap();
        break;
      default:
        return;
    }
  });
}

init();
