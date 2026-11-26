// Listen & watch checklist on /music/. The list lives on mr-ray (notes/listen.md, served by the
// inbox service): anyone can read it; adding, checking off, and deleting need the home network,
// Tailscale, or the inbox login (asked for right here).

const $ = (id) => document.getElementById(id);
const API = "/inbox/listen";
let data = { items: [], version: "", edit: false };

function say(text) {
  $("lwMsg").textContent = text || "";
}

function row(it) {
  const li = document.createElement("li");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = Boolean(it.done);
  box.disabled = !data.edit;
  box.title = data.edit
    ? it.done
      ? "Mark not done"
      : "Mark done"
    : "Log in to check off";
  box.onchange = () => send("toggle", { i: it.i, v: data.version });
  const t = document.createElement("span");
  t.className = "t";
  const name = document.createElement(it.link ? "a" : "span");
  name.textContent = it.title;
  if (it.link) {
    name.href = it.link;
    name.target = "_blank";
    name.rel = "noopener";
  }
  t.append(name);
  const meta = [it.by, it.done ? `done ${it.done}` : ""]
    .filter(Boolean)
    .join(" · ");
  if (meta) {
    const by = document.createElement("span");
    by.className = "by";
    by.textContent = meta;
    t.append(by);
  }
  li.append(box, t);
  if (data.edit) {
    const x = document.createElement("button");
    x.className = "x";
    x.type = "button";
    x.textContent = "×";
    x.title = "Delete";
    x.setAttribute("aria-label", `Delete ${it.title}`);
    x.onclick = () => {
      if (confirm(`Delete "${it.title}"?`))
        send("delete", { i: it.i, v: data.version });
    };
    li.append(x);
  }
  return li;
}

function render() {
  const todo = data.items.filter((it) => !it.done);
  const done = data.items
    .filter((it) => it.done)
    .sort((a, b) => b.done.localeCompare(a.done));
  $("lwTodo").replaceChildren(...todo.map(row));
  if (!todo.length) {
    const li = document.createElement("li");
    li.className = "by";
    li.textContent = data.items.length
      ? "All caught up."
      : "Nothing on the list yet.";
    $("lwTodo").append(li);
  }
  $("lwDone").replaceChildren(...done.map(row));
  $("lwDoneN").textContent = done.length;
  $("lwDoneBox").hidden = !done.length;
  $("lwCount").textContent = todo.length ? `${todo.length} to go` : "";
  $("lwAdd").hidden = !data.edit;
  $("lwEdit").hidden = data.edit || !$("lwLogin").hidden;
}

async function load() {
  try {
    const r = await fetch(`${API}.json`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
    render();
  } catch {
    say("The list isn't available right now.");
  }
}

async function send(action, fields) {
  say(action === "add" ? "Adding (looking up the title)…" : "");
  try {
    const r = await fetch(`${API}/${action}`, {
      method: "POST",
      body: new URLSearchParams(fields),
      credentials: "same-origin",
    });
    if (r.status === 401) {
      // not home, and the login expired
      data.edit = false;
      $("lwLogin").hidden = false;
      render();
      say("Log in again to edit.");
      return false;
    }
    data = await r.json();
    render();
    say(data.msg);
    return true;
  } catch {
    say("Couldn't reach the server.");
    load();
    return false;
  }
}

$("lwAdd").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target,
    btn = f.querySelector("button");
  btn.disabled = true;
  if (await send("add", { link: f.link.value, title: f.title.value }))
    f.reset();
  btn.disabled = false;
  f.link.focus();
};

$("lwEdit").onclick = () => {
  $("lwLogin").hidden = false;
  $("lwEdit").hidden = true;
  $("lwLogin").username.focus();
};

$("lwLogin").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  say("Logging in…");
  const r = await fetch("/inbox/login", {
    method: "POST",
    body: new URLSearchParams(new FormData(f)),
    redirect: "manual",
    credentials: "same-origin",
  }).catch(() => null);
  if (!r) return say("Couldn't reach the server.");
  if (r.type !== "opaqueredirect") {
    // success is a redirect; anything else is a refusal
    f.password.value = "";
    return say(
      r.status === 429
        ? "Too many tries. Wait a few minutes."
        : "Wrong username or password.",
    );
  }
  f.reset();
  f.hidden = true;
  say("");
  load();
};

load();
