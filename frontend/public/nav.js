// Shared top bar for cesiumlab.net's own tools (Inbox, Notes, Tasks, HQ, Status, Music, Docs).
// One file, used by every page that has <script src="/nav.js" defer></script>; edit LINKS here
// and every page updates. It inserts a slim bar at the top of the page and highlights the
// current app. Plain dark style (not the retro look of the public pages).
(() => {
  const LINKS = [
    ["Home", "/"],
    ["Inbox", "/inbox/"],
    ["Notes", "/inbox/notes/"],
    ["Tasks", "/tasks/"],
    ["HQ", "/hq/"],
    ["Status", "/inbox/status"],
    ["Music", "/music/"],
    ["Docs ↗", "https://docs.cesiumlab.net/docs/"],
    ["Music notes ↗", "https://docs.cesiumlab.net/music/"],
  ];
  function build() {
    if (document.getElementById("cl-nav")) return;
    // The current app = the longest same-site link the address starts with.
    const here = location.pathname;
    const mine = LINKS.filter(
      ([, h]) =>
        h.startsWith("/") &&
        (h === "/" ? here === "/" : here.startsWith(h.replace(/\/$/, ""))),
    ).sort((a, b) => b[1].length - a[1].length)[0];
    const css = document.createElement("style");
    css.textContent = `
#cl-nav{position:relative;z-index:30;display:flex;gap:2px;overflow-x:auto;white-space:nowrap;scrollbar-width:none;
  background:#141414;border-bottom:1px solid #2a2a2a;padding:0 10px;font:13px/1 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
#cl-nav::-webkit-scrollbar{display:none}
#cl-nav a{display:inline-block;padding:8px 9px;color:#9b9b98;text-decoration:none;border-bottom:2px solid transparent}
#cl-nav a:hover{color:#e9e9e7}
#cl-nav a.here{color:#e9e9e7;border-bottom-color:#e9e9e7}
#cl-nav .sep{flex:1}`;
    const bar = document.createElement("nav");
    bar.id = "cl-nav";
    bar.setAttribute("aria-label", "cesiumlab.net");
    LINKS.forEach(([label, href], i) => {
      if (i === LINKS.length - 2)
        bar.append(
          Object.assign(document.createElement("span"), { className: "sep" }),
        );
      const a = document.createElement("a");
      a.href = href;
      a.textContent = label;
      if (mine && mine[1] === href) {
        a.className = "here";
        a.setAttribute("aria-current", "page");
      }
      if (!href.startsWith("/")) {
        a.target = "_blank";
        a.rel = "noopener";
      }
      bar.append(a);
    });
    if (!document.getElementById("cl-nav-css")) {
      css.id = "cl-nav-css";
      document.head.append(css);
    }
    document.body.prepend(bar);
  }
  // Pages that swap their <body> in place (the inbox's day buttons) call clNav() afterwards.
  window.clNav = build;
  if (document.body) build();
  else document.addEventListener("DOMContentLoaded", build);
})();
