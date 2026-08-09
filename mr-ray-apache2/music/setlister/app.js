(() => {
  "use strict";
  const STORE = "setlister-library-v1",
    ROOTS = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"],
    PITCH = {
      C: 0,
      "C♯": 1,
      "D♭": 1,
      D: 2,
      "D♯": 3,
      "E♭": 3,
      E: 4,
      F: 5,
      "F♯": 6,
      "G♭": 6,
      G: 7,
      "G♯": 8,
      "A♭": 8,
      A: 9,
      "A♯": 10,
      "B♭": 10,
      B: 11,
    };
  const $ = (id) => document.getElementById(id),
    uid = () =>
      crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    blank = () => ({
      version: 1,
      songs: [],
      setlists: [{ id: uid(), name: "Untitled Set", songIds: [] }],
      activeSetlistId: null,
    });
  let dirty = false,
    dragged = null,
    state = load();
  if (
    !state.activeSetlistId ||
    !state.setlists.some((s) => s.id === state.activeSetlistId)
  )
    state.activeSetlistId = state.setlists[0].id;
  function normalize(v) {
    if (!v || !Array.isArray(v.songs) || !Array.isArray(v.setlists))
      return blank();
    const songs = v.songs.map((s) => ({
        id: String(s.id || uid()),
        title: String(s.title || "Untitled"),
        artist: String(s.artist || ""),
        key: String(s.key || "C major"),
        bpm: Number(s.bpm) || 120,
        energy: Math.min(10, Math.max(1, Number(s.energy) || 5)),
        durationSeconds: Math.max(0, Number(s.durationSeconds) || 0),
        tags: Array.isArray(s.tags) ? s.tags.map(String) : [],
        notes: String(s.notes || ""),
      })),
      ids = new Set(songs.map((s) => s.id)),
      setlists = v.setlists.map((s) => ({
        id: String(s.id || uid()),
        name: String(s.name || "Untitled Set"),
        songIds: Array.isArray(s.songIds)
          ? s.songIds.map(String).filter((id) => ids.has(id))
          : [],
      }));
    if (!setlists.length)
      setlists.push({ id: uid(), name: "Untitled Set", songIds: [] });
    return {
      version: 1,
      songs,
      setlists,
      activeSetlistId: String(v.activeSetlistId || setlists[0].id),
    };
  }
  function load() {
    try {
      return normalize(JSON.parse(localStorage.getItem(STORE)));
    } catch {
      return blank();
    }
  }
  function save(mark = true) {
    localStorage.setItem(STORE, JSON.stringify(state));
    if (mark) dirty = true;
    status();
  }
  function status() {
    $("saveStatus").textContent = dirty
      ? "Browser backup saved • download JSON to update your file"
      : "Browser backup saved";
    $("saveStatus").classList.toggle("dirty", dirty);
  }
  function set() {
    return (
      state.setlists.find((s) => s.id === state.activeSetlistId) ||
      state.setlists[0]
    );
  }
  function song(id) {
    return state.songs.find((s) => s.id === id);
  }
  function duration(n) {
    n = Math.round(Number(n) || 0);
    const h = Math.floor(n / 3600),
      m = Math.floor((n % 3600) / 60),
      s = n % 60;
    return h
      ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
      : `${m}:${String(s).padStart(2, "0")}`;
  }
  function parseDuration(t) {
    const p = String(t).trim().split(":").map(Number);
    return p.some(Number.isNaN)
      ? 0
      : p.length === 3
        ? p[0] * 3600 + p[1] * 60 + p[2]
        : p.length === 2
          ? p[0] * 60 + p[1]
          : 0;
  }
  function notice(msg, type = "") {
    const n = $("notice");
    n.textContent = msg;
    n.className = `notice ${type}`;
    n.hidden = false;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => (n.hidden = true), 4500);
  }
  function keyOptions() {
    for (const root of ROOTS)
      for (const mode of ["major", "minor"]) {
        const value = `${root} ${mode}`;
        $("key").add(new Option(value, value));
        $("keyFilter").add(new Option(value, value));
      }
  }
  function render() {
    filters();
    library();
    setlists();
    summary();
    status();
  }
  function filters() {
    const old = $("tagFilter").value,
      tags = [
        ...new Set(
          state.songs
            .flatMap((s) => s.tags)
            .map((t) => t.trim())
            .filter(Boolean),
        ),
      ].sort((a, b) => a.localeCompare(b));
    $("tagFilter").replaceChildren(
      new Option("All tags", ""),
      ...tags.map((t) => new Option(t, t)),
    );
    if (tags.includes(old)) $("tagFilter").value = old;
  }
  function visibleSongs() {
    const q = $("searchInput").value.trim().toLowerCase(),
      k = $("keyFilter").value,
      t = $("tagFilter").value;
    return state.songs
      .filter(
        (s) =>
          (!q ||
            [s.title, s.artist, s.notes, ...s.tags]
              .join(" ")
              .toLowerCase()
              .includes(q)) &&
          (!k || s.key === k) &&
          (!t || s.tags.includes(t)),
      )
      .sort((a, b) => a.title.localeCompare(b.title));
  }
  function library() {
    const body = $("songRows");
    body.textContent = "";
    $("libraryEmpty").hidden = state.songs.length > 0;
    for (const s of visibleSongs()) {
      const row =
          $("songRowTemplate").content.firstElementChild.cloneNode(true),
        link = row.querySelector(".song-link");
      link.textContent = s.title;
      link.onclick = () => openSong(s);
      row.querySelector(".artist").textContent = s.artist || "Unknown artist";
      row.querySelector(".tags").textContent = s.tags.join(" · ");
      row.querySelector(".key-cell").textContent = s.key;
      row.querySelector(".bpm-cell").textContent = s.bpm;
      const e = row.querySelector(".energy-cell");
      e.append(`${s.energy} `);
      const meter = document.createElement("span"),
        bar = document.createElement("i");
      meter.className = "meter";
      bar.style.width = `${s.energy * 10}%`;
      meter.append(bar);
      e.append(meter);
      row.querySelector(".add-track").onclick = () => addTrack(s.id);
      const deleteButton = row.querySelector(".delete-song");
      deleteButton.setAttribute("aria-label", `Delete ${s.title}`);
      deleteButton.onclick = () => deleteSong(s.id);
      body.append(row);
    }
  }
  function setlists() {
    const active = set();
    $("setlistSelect").replaceChildren(
      ...state.setlists.map((s) => new Option(s.name, s.id)),
    );
    $("setlistSelect").value = active.id;
    $("setlistName").value = active.name;
    const list = $("setlistTracks");
    list.textContent = "";
    const songs = active.songIds.map(song).filter(Boolean);
    songs.forEach((s, i) => {
      if (i) {
        const c = compatibility(songs[i - 1], s),
          tr = document.createElement("li");
        tr.className = `transition ${c.score < 45 ? "bad" : c.score < 70 ? "warn" : ""}`;
        tr.textContent = `↳ ${c.score}% — ${c.reasons.join(" · ")}`;
        list.append(tr);
      }
      const item = $("trackTemplate").content.firstElementChild.cloneNode(true);
      item.dataset.index = i;
      item.querySelector(".track-number").textContent = String(i + 1).padStart(
        2,
        "0",
      );
      item.querySelector(".track-info strong").textContent = s.title;
      item.querySelector(".track-info span").textContent =
        s.artist || "Unknown artist";
      item.querySelector(".track-meta").textContent =
        `${s.key} · ${s.bpm} BPM · E${s.energy}`;
      item.querySelector(".move-up").disabled = i === 0;
      item.querySelector(".move-down").disabled = i === songs.length - 1;
      item.querySelector(".move-up").onclick = () => move(i, i - 1);
      item.querySelector(".move-down").onclick = () => move(i, i + 1);
      item.querySelector(".remove-track").onclick = () => remove(i);
      item.ondragstart = () => {
        dragged = i;
        item.classList.add("dragging");
      };
      item.ondragend = () => {
        dragged = null;
        document
          .querySelectorAll(".track")
          .forEach((x) => x.classList.remove("dragging", "drop-target"));
      };
      item.ondragover = (e) => {
        e.preventDefault();
        item.classList.add("drop-target");
      };
      item.ondragleave = () => item.classList.remove("drop-target");
      item.ondrop = (e) => {
        e.preventDefault();
        if (dragged !== null && dragged !== i) move(dragged, i);
      };
      list.append(item);
    });
    $("setlistEmpty").hidden = !!songs.length;
    $("setlistDuration").textContent = duration(
      songs.reduce((n, s) => n + s.durationSeconds, 0),
    );
  }
  function summary() {
    $("songCount").textContent = state.songs.length;
    $("setCount").textContent = state.setlists.length;
    $("totalRuntime").textContent = duration(
      set()
        .songIds.map(song)
        .filter(Boolean)
        .reduce((n, s) => n + s.durationSeconds, 0),
    );
  }
  function splitKey(k) {
    const i = k.lastIndexOf(" ");
    return { root: k.slice(0, i), mode: k.slice(i + 1) };
  }
  function compatibility(a, b) {
    let score = 0,
      reasons = [];
    const ka = splitKey(a.key),
      kb = splitKey(b.key),
      pa = PITCH[ka.root] ?? 0,
      pb = PITCH[kb.root] ?? 0,
      d = (pb - pa + 12) % 12;
    if (a.key === b.key) {
      score += 40;
      reasons.push("same key");
    } else if (
      ka.mode !== kb.mode &&
      ((ka.mode === "major" && d === 9) || (ka.mode === "minor" && d === 3))
    ) {
      score += 38;
      reasons.push("relative key");
    } else if (d === 5 || d === 7) {
      score += 30;
      reasons.push("neighboring fifth");
    } else if (pa === pb) {
      score += 25;
      reasons.push("parallel key");
    } else {
      score += 10;
      reasons.push("key contrast");
    }
    const td = Math.min(
      Math.abs(a.bpm - b.bpm),
      Math.abs(a.bpm * 2 - b.bpm),
      Math.abs(a.bpm - b.bpm * 2),
    );
    if (td <= 3) {
      score += 30;
      reasons.push("tempo locked");
    } else if (td <= 8) {
      score += 24;
      reasons.push(`${td.toFixed(0)} BPM shift`);
    } else if (td <= 15) {
      score += 15;
      reasons.push(`${td.toFixed(0)} BPM jump`);
    } else {
      score += 4;
      reasons.push("large tempo jump");
    }
    const ed = Math.abs(a.energy - b.energy);
    if (ed <= 1) {
      score += 20;
      reasons.push("smooth energy");
    } else if (ed <= 3) {
      score += 14;
      reasons.push(`${ed}-point energy change`);
    } else {
      score += 5;
      reasons.push("dramatic energy change");
    }
    if (a.tags.some((t) => b.tags.includes(t))) {
      score += 10;
      reasons.push("shared tags");
    }
    return { score: Math.min(100, score), reasons };
  }
  async function lookupSong() {
    const title = $("title").value.trim(),
      artist = $("artist").value.trim(),
      button = $("lookupSong"),
      box = $("lookupResults");
    if (title.length < 2) {
      $("lookupStatus").textContent = "Enter a song title first.";
      return;
    }
    button.disabled = true;
    $("lookupStatus").textContent = "Searching…";
    box.hidden = true;
    box.textContent = "";
    try {
      const params = new URLSearchParams({ title, artist }),
        endpoint = `/api/setlister/search?${params}`,
        response = await fetch(endpoint, {
          headers: { Accept: "application/json" },
        }),
        raw = await response.text();
      let payload;
      try {
        payload = JSON.parse(raw);
      } catch {
        throw Error(`Song API returned ${response.status} ${response.statusText || "with HTML"} at ${endpoint}. Check /api/setlister/health on this hostname.`);
      }
      if (!response.ok)
        throw Error(payload.error || `Search failed (${response.status})`);
      const results = Array.isArray(payload.results) ? payload.results : [];
      $("lookupStatus").textContent = results.length
        ? `Top ${results.length} matches from GetSongBPM — choose one.`
        : "No matches found.";
      results.forEach((result, index) => {
        const option = document.createElement("button"),
          description = document.createElement("span"),
          name = document.createElement("b"),
          meta = document.createElement("small");
        option.type = "button";
        option.className = "lookup-result";
        const rank = document.createElement("span");
        rank.className = "lookup-rank";
        rank.textContent = `#${index + 1}`;
        name.textContent = result.title || "Untitled";
        meta.textContent = [
          result.artist,
          result.album || null,
          result.year || null,
          result.key,
          result.bpm ? `${result.bpm} BPM` : null,
        ]
          .filter(Boolean)
          .join(" · ");
        description.append(name, meta);
        const use = document.createElement("span");
        use.textContent = "USE →";
        option.append(rank, description, use);
        option.onclick = () => applyLookup(result);
        box.append(option);
      });
      box.hidden = !results.length;
    } catch (error) {
      $("lookupStatus").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }
  function applyLookup(result) {
    if (result.title) $("title").value = result.title;
    if (result.artist) $("artist").value = result.artist;
    if (result.key && [...$("key").options].some((o) => o.value === result.key))
      $("key").value = result.key;
    if (result.bpm) $("bpm").value = result.bpm;
    if (Number.isFinite(Number(result.danceability)))
      $("energy").value = Math.max(
        1,
        Math.min(10, Math.round(Number(result.danceability) / 10)),
      );
    const current = $("tags")
        .value.split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      incoming = Array.isArray(result.tags) ? result.tags : [];
    $("tags").value = [...new Set([...current, ...incoming])].join(", ");
    $("lookupResults").hidden = true;
    $("lookupStatus").textContent =
      "Song data applied. Review it before saving.";
  }
  function openSong(s = null) {
    $("songForm").reset();
    $("songId").value = s?.id || "";
    $("dialogHeading").textContent = s ? "EDIT SONG" : "ADD SONG";
    $("title").value = s?.title || "";
    $("artist").value = s?.artist || "";
    $("key").value = s?.key || "C major";
    $("bpm").value = s?.bpm || 120;
    $("energy").value = s?.energy || 5;
    $("duration").value = s?.durationSeconds ? duration(s.durationSeconds) : "";
    $("tags").value = s?.tags.join(", ") || "";
    $("notes").value = s?.notes || "";
    $("lookupResults").hidden = true;
    $("lookupResults").textContent = "";
    $("lookupStatus").textContent =
      "Search by title and artist to fill key and BPM.";
    $("songDialog").showModal();
    $("title").focus();
  }
  function saveSong() {
    const id = $("songId").value,
      s = {
        id: id || uid(),
        title: $("title").value.trim(),
        artist: $("artist").value.trim(),
        key: $("key").value,
        bpm: Number($("bpm").value),
        energy: Number($("energy").value),
        durationSeconds: parseDuration($("duration").value),
        tags: [
          ...new Set(
            $("tags")
              .value.split(",")
              .map((x) => x.trim())
              .filter(Boolean),
          ),
        ],
        notes: $("notes").value.trim(),
      };
    if (!s.title) return;
    const i = state.songs.findIndex((x) => x.id === id);
    if (i >= 0) state.songs[i] = s;
    else state.songs.push(s);
    save();
    render();
    notice(i >= 0 ? "Song updated." : "Song added.", "success");
    return true;
  }
  function deleteSong(id) {
    const target = song(id);
    if (!target) return;
    const uses = state.setlists.reduce(
      (total, item) => total + item.songIds.filter((songId) => songId === id).length,
      0,
    );
    const usageWarning = uses
      ? ` It will also be removed from ${uses} position${uses === 1 ? "" : "s"} across your setlists.`
      : "";
    const confirmed = confirm(
      `Delete “${target.title}” from the song library?${usageWarning} ` +
        "Download your library first if you want a backup. Are you sure?",
    );
    if (!confirmed) return;
    state.songs = state.songs.filter((item) => item.id !== id);
    state.setlists.forEach((item) => {
      item.songIds = item.songIds.filter((songId) => songId !== id);
    });
    save();
    render();
    notice(`“${target.title}” was deleted from the library and all setlists.`, "success");
  }
  function addTrack(id) {
    set().songIds.push(id);
    save();
    render();
  }
  function remove(i) {
    set().songIds.splice(i, 1);
    save();
    render();
  }
  function move(from, to) {
    const ids = set().songIds,
      [id] = ids.splice(from, 1);
    ids.splice(to, 0, id);
    save();
    render();
  }
  function newSet() {
    const s = {
      id: uid(),
      name: `Setlist ${state.setlists.length + 1}`,
      songIds: [],
    };
    state.setlists.push(s);
    state.activeSetlistId = s.id;
    save();
    render();
    $("setlistName").select();
  }
  function deleteSet() {
    const current = set();
    if (state.setlists.length === 1) {
      const confirmed = confirm(
        `Reset “${current.name}”? This removes every song from the setlist. ` +
          "Download your library first if you want a backup. Are you sure?",
      );
      if (!confirmed) return;
      current.name = "Untitled Set";
      current.songIds = [];
      save();
      render();
      notice("Setlist reset. Your song library was not changed.", "success");
      return;
    }
    if (!confirm(`Delete “${current.name}”? Download your library first if you want a backup. Are you sure?`)) return;
    state.setlists = state.setlists.filter(
      (s) => s.id !== state.activeSetlistId,
    );
    state.activeSetlistId = state.setlists[0].id;
    save();
    render();
  }
  function newLibrary() {
    if (
      !confirm(
        "Start a new library? Download the current one first if you need it.",
      )
    )
      return;
    state = blank();
    state.activeSetlistId = state.setlists[0].id;
    save();
    render();
    notice("New library created.", "success");
  }
  function download() {
    const blob = new Blob(
        [
          JSON.stringify(
            { ...state, exportedAt: new Date().toISOString() },
            null,
            2,
          ),
        ],
        { type: "application/json" },
      ),
      a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `music-library-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    dirty = false;
    status();
    notice("Library downloaded.", "success");
  }
  async function upload(file) {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      if (!Array.isArray(parsed.songs) || !Array.isArray(parsed.setlists))
        throw Error("Expected “songs” and “setlists” arrays.");
      if (
        (state.songs.length || set().songIds.length) &&
        !confirm("Replace the current browser library with this file?")
      )
        return;
      state = normalize(parsed);
      if (!state.setlists.some((s) => s.id === state.activeSetlistId))
        state.activeSetlistId = state.setlists[0].id;
      dirty = false;
      save(false);
      render();
      notice(
        `Loaded ${state.songs.length} songs from ${file.name}.`,
        "success",
      );
    } catch (e) {
      notice(`Could not load JSON: ${e.message}`);
    } finally {
      $("fileInput").value = "";
    }
  }
  keyOptions();
  $("addSong").onclick = () => openSong();
  $("lookupSong").onclick = lookupSong;
  $("closeDialog").onclick = $("cancelDialog").onclick = () =>
    $("songDialog").close();
  $("songForm").onsubmit = (event) => event.preventDefault();
  $("saveSongButton").onclick = () => {
    if (!$("songForm").reportValidity()) return;
    if (saveSong()) $("songDialog").close();
  };
  const songFields = ["title", "artist", "key", "bpm", "energy", "duration", "tags", "notes"].map($);
  songFields.forEach((field, index) => {
    field.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey) return;
      event.preventDefault();
      const next = songFields[index + 1];
      if (next) {
        next.focus();
        if (typeof next.select === "function" && next.tagName !== "SELECT") next.select();
      } else {
        field.blur();
      }
    });
  });
  $("searchInput").oninput = library;
  $("keyFilter").onchange = library;
  $("tagFilter").onchange = library;
  $("newSetlist").onclick = newSet;
  $("deleteSetlist").onclick = deleteSet;
  $("setlistSelect").onchange = (e) => {
    state.activeSetlistId = e.target.value;
    save();
    render();
  };
  $("setlistName").oninput = (e) => {
    set().name = e.target.value || "Untitled Set";
    save();
    summary();
    const o = [...$("setlistSelect").options].find((o) => o.value === set().id);
    if (o) o.textContent = set().name;
  };
  $("newLibrary").onclick = newLibrary;
  $("downloadLibrary").onclick = download;
  $("fileInput").onchange = (e) => upload(e.target.files[0]);
  $("printSetlist").onclick = () => print();
  render();
})();
