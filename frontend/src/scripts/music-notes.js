// /music/: the Licks to learn, Song ideas, and Music tools sections, filled from the Notes
// buckets on mr-ray (GET /inbox/music.json, public and read-only). You edit them in Notes; an
// "Edit in Notes" link shows only when you're home, on Tailscale, or logged in.

function row(it) {
  const li = document.createElement("li");
  const link = it.links[0];
  const name = document.createElement(link ? "a" : "span");
  name.className = "mu-plus" + (link ? "" : " mu-plain");
  name.textContent = it.title;
  if (link) {
    name.href = link;
    name.target = "_blank";
    name.rel = "noopener";
  }
  li.append(name);
  const meta = [it.by, it.note].filter(Boolean).join(" · ");
  if (meta) {
    const small = document.createElement("small");
    small.textContent = meta;
    li.append(small);
  }
  return li;
}

async function load() {
  let data;
  try {
    const r = await fetch("/inbox/music.json", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
  } catch {
    document.querySelectorAll("[data-bucket] .mu-links").forEach((ul) => {
      ul.innerHTML =
        "<li><small>Couldn't load this list right now.</small></li>";
    });
    return;
  }
  for (const sec of data.sections) {
    const box = document.querySelector(`[data-bucket="${sec.bucket}"]`);
    if (!box) continue;
    const ul = box.querySelector(".mu-links");
    ul.replaceChildren(...sec.items.map(row));
    if (!sec.items.length) {
      const li = document.createElement("li");
      li.innerHTML = "<small>Nothing here yet.</small>";
      ul.append(li);
    }
    box.querySelector(".mu-editnotes").hidden = !data.edit;
  }
}

load();
