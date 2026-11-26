// Tuner (/music/tuner/): microphone -> pitch (YIN) -> nearest note or string, shown as a needle
// or a strobe. Everything runs in the browser; no audio is stored or sent anywhere.

const $ = (id) => document.getElementById(id);
const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
// Strings as MIDI note numbers, lowest first.
const PRESETS = {
  chromatic: [],
  guitar: [40, 45, 50, 55, 59, 64],
  dropd: [38, 45, 50, 55, 59, 64],
  bass4: [28, 33, 38, 43],
  bass5: [23, 28, 33, 38, 43],
};
const IN_TUNE = 2; // cents

const store = {
  get(k, d) {
    try {
      return localStorage.getItem("tuner." + k) ?? d;
    } catch {
      return d;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem("tuner." + k, v);
    } catch {}
  },
};

let a4 = Number(store.get("a4", 440)) || 440;
let preset = store.get("preset", "chromatic");
let view = store.get("view", "needle");
let volume = Number(store.get("volume", 0.4));
if (!(preset in PRESETS)) preset = "chromatic";

let ctx = null,
  analyser = null,
  stream = null,
  buf = null;
let running = false,
  lastAnalysis = 0,
  lastHeard = 0;
let history = []; // recent frequencies, for a steady reading
let targetMidi = 69; // note the reference tone plays (follows what you play)
let cents = 0,
  shownDeg = 0,
  strobeA = 0,
  strobeB = 0,
  lastFrame = 0;
let osc = null,
  gain = null;

const hz = (midi) => a4 * 2 ** ((midi - 69) / 12);
const noteOf = (midi) => ({
  name: NAMES[((midi % 12) + 12) % 12],
  octave: Math.floor(midi / 12) - 1,
});

// ---------- pitch detection runs in a worker (tuner-worker.js), never on the page thread ----------
const worker = new Worker(new URL("./tuner-worker.js", import.meta.url), {
  type: "module",
});
let busy = false; // at most one analysis in flight: if it's slow, frames are skipped, not queued
worker.onmessage = (e) => {
  busy = false;
  if (running) heard(e.data.f, performance.now());
};

function median(a) {
  const s = [...a].sort((p, q) => p - q);
  return s[s.length >> 1];
}

// ---------- reading -> display ----------
function show(freq) {
  const root = document.querySelector(".tu-workspace");
  const gaugeIdle = freq == null;
  $("needleView").classList.toggle("idle", gaugeIdle);
  $("strobeView").classList.toggle("idle", gaugeIdle);
  if (freq == null) {
    $("noteName").textContent = "—";
    $("noteOctave").textContent = "";
    $("hz").textContent = $("cents").textContent = "—";
    $("stringHint").textContent = running ? "listening… play one note" : "";
    $("noteName").parentElement.classList.remove("ok");
    root.classList.remove("ok");
    cents = 0;
    markStrings(null, false);
    return;
  }
  const midi = 69 + 12 * Math.log2(freq / a4);
  const strings = PRESETS[preset];
  let target;
  if (strings.length) {
    target = strings.reduce(
      (p, s) => (Math.abs(s - midi) < Math.abs(p - midi) ? s : p),
      strings[0],
    );
  } else {
    target = Math.round(midi);
  }
  targetMidi = target;
  cents = (midi - target) * 100;
  const ok = Math.abs(cents) <= IN_TUNE;
  const n = noteOf(target);
  $("noteName").textContent = n.name;
  $("noteOctave").textContent = n.octave;
  $("hz").textContent = freq.toFixed(1);
  $("cents").textContent = (cents > 0 ? "+" : "") + cents.toFixed(0);
  $("target").textContent = hz(target).toFixed(1);
  $("noteName").parentElement.classList.toggle("ok", ok);
  root.classList.toggle("ok", ok);
  let hint = ok ? "in tune" : cents < 0 ? "flat: tune up" : "sharp: tune down";
  if (strings.length) {
    const idx = strings.indexOf(target);
    hint = `string ${strings.length - idx} (${n.name}${n.octave}) · ` + hint;
    if (Math.abs(cents) > 50) hint += " a lot";
  }
  $("stringHint").textContent = hint;
  markStrings(target, ok);
  if (osc) osc.frequency.setTargetAtTime(hz(targetMidi), ctx.currentTime, 0.02);
}

function heard(f, t) {
  if (f) {
    // A jump of more than a semitone means a new note: start the average over.
    if (history.length && Math.abs(12 * Math.log2(f / median(history))) > 1)
      history = [];
    history.push(f);
    if (history.length > 5) history.shift();
    lastHeard = t;
    show(median(history));
  } else if (t - lastHeard > 1500 && history.length) {
    history = [];
    show(null);
  }
}

function frame(t) {
  if (!running) return;
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (t - lastFrame) / 1000 || 0);
  lastFrame = t;
  if (t - lastAnalysis > 60 && !busy) {
    lastAnalysis = t;
    analyser.getFloatTimeDomainData(buf);
    busy = true;
    const x = buf.slice(); // a copy goes to the worker; buf is reused
    worker.postMessage({ x, sr: ctx.sampleRate }, [x.buffer]);
  }
  // Needle eases toward the reading; strobe drifts at a speed proportional to the error.
  const c = Math.max(-50, Math.min(50, cents));
  shownDeg += (c * 0.9 - shownDeg) * Math.min(1, dt * 14);
  $("needle").setAttribute("transform", `rotate(${shownDeg.toFixed(2)})`);
  if (history.length) {
    strobeA = (strobeA + c * 3 * dt) % 36;
    strobeB = (strobeB + c * 1 * dt) % 12;
  }
  $("strobeA").style.backgroundPosition = `${strobeA}px 0`;
  $("strobeB").style.backgroundPosition = `${strobeB}px 0`;
}

// ---------- mic ----------
let starting = false;
async function start() {
  if (running || starting) return; // e.g. Space on the focused Start button fires twice
  starting = true;
  try {
    await openMic();
  } finally {
    starting = false;
  }
}

async function openMic() {
  $("msg").textContent = "";
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    $("msg").textContent =
      "The microphone needs a secure page: open https://cesiumlab.net/music/tuner/.";
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
  } catch (e) {
    $("msg").textContent =
      e.name === "NotAllowedError"
        ? "Microphone blocked. Allow it for this site (address bar) and try again."
        : `Couldn't open the microphone (${e.name}).`;
    return;
  }
  ctx ??= new AudioContext();
  await ctx.resume();
  analyser = ctx.createAnalyser();
  // ~85 ms of audio at any mic rate: long enough for a 5-string bass's low B.
  analyser.fftSize =
    ctx.sampleRate > 96000 ? 16384 : ctx.sampleRate > 48000 ? 8192 : 4096;
  buf = new Float32Array(analyser.fftSize);
  ctx.createMediaStreamSource(stream).connect(analyser);
  running = true;
  history = [];
  $("startStop").textContent = "■ Stop";
  $("startStop").classList.remove("primary");
  show(null);
  requestAnimationFrame(frame);
}

function stop() {
  running = false;
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  history = [];
  show(null);
  $("stringHint").textContent = "";
  $("startStop").textContent = "🎤 Start tuner";
  $("startStop").classList.add("primary");
}

// ---------- reference tone ----------
function toneOn(midi = targetMidi) {
  ctx ??= new AudioContext();
  ctx.resume();
  targetMidi = midi;
  if (!osc) {
    osc = ctx.createOscillator();
    gain = ctx.createGain();
    osc.type = "triangle";
    gain.gain.value = 0;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
  }
  osc.frequency.setValueAtTime(hz(midi), ctx.currentTime);
  gain.gain.setTargetAtTime(volume * 0.5, ctx.currentTime, 0.02);
  $("refTone").classList.add("on");
  $("refTone").textContent =
    `♪ ${noteOf(midi).name}${noteOf(midi).octave} · stop`;
  $("target").textContent = hz(midi).toFixed(1);
}
function toneOff() {
  if (!osc) return;
  gain.gain.setTargetAtTime(0, ctx.currentTime, 0.03);
  const o = osc;
  setTimeout(() => o.stop(), 200);
  osc = gain = null;
  $("refTone").classList.remove("on");
  $("refTone").textContent = "♪ Reference tone";
}

// ---------- setup panel ----------
function buildTicks() {
  const g = $("ticks");
  for (let c = -50; c <= 50; c += 5) {
    const a = (c * 0.9 * Math.PI) / 180,
      major = c % 25 === 0;
    const r1 = 95,
      r2 = major ? 80 : 87;
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", (Math.sin(a) * r1).toFixed(2));
    l.setAttribute("y1", (-Math.cos(a) * r1).toFixed(2));
    l.setAttribute("x2", (Math.sin(a) * r2).toFixed(2));
    l.setAttribute("y2", (-Math.cos(a) * r2).toFixed(2));
    if (major) l.classList.add("major");
    g.append(l);
  }
}

function buildStrings() {
  const box = $("strings");
  box.replaceChildren(
    ...PRESETS[preset].map((m) => {
      const b = document.createElement("button");
      const n = noteOf(m);
      b.className = "small";
      b.dataset.midi = m;
      b.textContent = n.name + n.octave;
      b.title = `Play ${n.name}${n.octave} (${hz(m).toFixed(1)} Hz)`;
      b.onclick = () => (osc && targetMidi === m ? toneOff() : toneOn(m));
      return b;
    }),
  );
  box.hidden = !PRESETS[preset].length;
}
function markStrings(midi, ok) {
  $("strings")
    .querySelectorAll("button")
    .forEach((b) => {
      const on = Number(b.dataset.midi) === midi;
      b.classList.toggle("active", on && !ok);
      b.classList.toggle("ok", on && ok);
    });
}

function setView(v) {
  view = v;
  store.set("view", v);
  $("needleView").hidden = v !== "needle";
  $("strobeView").hidden = v !== "strobe";
  $("modeLabel").textContent = v === "needle" ? "NEEDLE" : "STROBE";
  $("viewToggle").textContent = v === "needle" ? "Strobe view" : "Needle view";
}

function setA4(v) {
  a4 = Math.max(400, Math.min(480, Math.round(Number(v) || 440)));
  $("a4").value = a4;
  store.set("a4", a4);
  buildStrings();
  if (osc) osc.frequency.setValueAtTime(hz(targetMidi), ctx.currentTime);
}

buildTicks();
$("preset").value = preset;
$("a4").value = a4;
$("volume").value = volume;
buildStrings();
setView(view);
show(null);

$("startStop").onclick = () => (running ? stop() : start());
$("refTone").onclick = () => (osc ? toneOff() : toneOn());
$("viewToggle").onclick = () =>
  setView(view === "needle" ? "strobe" : "needle");
$("preset").onchange = (e) => {
  preset = e.target.value;
  store.set("preset", preset);
  buildStrings();
  history = [];
};
$("a4").onchange = (e) => setA4(e.target.value);
$("a4Down").onclick = () => setA4(a4 - 1);
$("a4Up").onclick = () => setA4(a4 + 1);
$("a4Reset").onclick = () => setA4(440);
$("volume").oninput = (e) => {
  volume = Number(e.target.value);
  store.set("volume", volume);
  if (gain) gain.gain.setTargetAtTime(volume * 0.5, ctx.currentTime, 0.02);
};
document.addEventListener("keydown", (e) => {
  if (
    e.target.closest("input, select, textarea") ||
    e.metaKey ||
    e.ctrlKey ||
    e.altKey
  )
    return;
  if (e.code === "Space") {
    e.preventDefault();
    running ? stop() : start();
  } else if (e.key === "v" || e.key === "V")
    setView(view === "needle" ? "strobe" : "needle");
  else if (e.key === "r" || e.key === "R") osc ? toneOff() : toneOn();
});
