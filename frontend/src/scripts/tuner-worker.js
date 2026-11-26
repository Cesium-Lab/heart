// Tuner pitch detection, off the page's main thread so a slow analysis can never freeze the
// tab. Gets {x: Float32Array, sr}, answers {f: Hz | null}.
const MIN_HZ = 25;
const MAX_HZ = 1500;

// Halve the sample rate (average pairs) until it's <= 24 kHz: ~4x less work, same accuracy
// for notes up to MAX_HZ.
function down(x, sr) {
  while (sr > 24000) {
    const y = new Float32Array(x.length >> 1);
    for (let i = 0; i < y.length; i++) y[i] = (x[2 * i] + x[2 * i + 1]) / 2;
    x = y;
    sr /= 2;
  }
  return [x, sr];
}

// YIN: cumulative mean normalized difference.
function detect(x, sr) {
  let rms = 0;
  for (let i = 0; i < x.length; i++) rms += x[i] * x[i];
  if (Math.sqrt(rms / x.length) < 0.01) return null; // too quiet
  const half = x.length >> 1;
  const minTau = Math.floor(sr / MAX_HZ);
  const maxTau = Math.min(half - 1, Math.ceil(sr / MIN_HZ));
  const d = new Float32Array(maxTau + 1);
  for (let tau = 1; tau <= maxTau; tau++) {
    let s = 0;
    for (let i = 0; i < half; i++) {
      const v = x[i] - x[i + tau];
      s += v * v;
    }
    d[tau] = s;
  }
  // Normalize; the first dip under the threshold is the period (avoids octave errors).
  let run = 0,
    best = -1;
  d[0] = 1;
  for (let tau = 1; tau <= maxTau; tau++) {
    run += d[tau];
    d[tau] = run ? (d[tau] * tau) / run : 1;
  }
  for (let tau = minTau; tau <= maxTau; tau++) {
    if (d[tau] < 0.12) {
      while (tau + 1 <= maxTau && d[tau + 1] < d[tau]) tau++;
      best = tau;
      break;
    }
  }
  if (best < 0) return null; // no clear pitch (noise, chord)
  // Parabolic interpolation around the dip for sub-sample accuracy.
  const a = d[best - 1] ?? d[best],
    b = d[best],
    c = d[best + 1] ?? d[best];
  const shift = (a - c) / (2 * (a - 2 * b + c)) || 0;
  return sr / (best + Math.max(-1, Math.min(1, shift)));
}

self.onmessage = (e) => {
  const [x, sr] = down(e.data.x, e.data.sr);
  self.postMessage({ f: detect(x, sr) });
};
