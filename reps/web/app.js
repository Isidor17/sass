"use strict";

const $ = (s, el = document) => el.querySelector(s);
const GROUP_COLORS = ["--g0", "--g1", "--g2", "--g3", "--g4", "--g5", "--g6", "--g7"].map(
  (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()
);
const EXERCISES = [
  "Développé couché", "Développé incliné", "Développé militaire", "Squat", "Front squat", "Soulevé de terre",
  "Soulevé de terre roumain", "Tractions", "Dips", "Rowing barre", "Rowing haltère", "Hip thrust", "Fentes",
  "Presse à cuisses", "Leg curl", "Leg extension", "Curl biceps", "Curl marteau", "Extension triceps",
  "Élévations latérales", "Écarté poulie", "Tirage vertical", "Pompes", "Burpees", "Gainage", "Mollets",
];
const HOOKS = ["Train like an athlete", "Athletic leg day", "Upper body", "Séance pecs", "Leg day", "Push day", "Pull day", "Séance dos", "Full body", "Séance épaules"];
const CTAS = ["Enregistre pour ta prochaine séance", "Abonne-toi pour la suite", "Tu tiens combien ? Dis-le en commentaire"];
const STYLE_DESC = { athletic: "Plan continu, zooms en coupe sèche, naturel", athletic_rapide: "Intro teaser, plans de 3 s, ambiance sombre", energique: "Coupes rapides, zooms punch", cinematique: "Zoom lent, tons froids", clean: "Naturel, sans effet" };
const LS_KEY = "reps.session.v1";

const state = {
  pid: null,
  project: null,
  excluded: new Set(),
  groups: [],
  style: "athletic",
  exercises: [],
};

/* ---------- utilitaires ---------- */
const fmt = (s) => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
};
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 7000 : 3500);
}
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
  return data;
}
const jsonPost = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function setStep(n) {
  document.querySelectorAll(".step-pill").forEach((p) => {
    const s = +p.dataset.step;
    p.classList.toggle("active", s === n);
    p.classList.toggle("done", s < n);
  });
}
function show(id) {
  const el = $(id);
  if (el.hidden) {
    el.hidden = false;
    el.classList.add("reveal");
  }
  return el;
}
function syncRange(el) {
  const p = ((el.value - el.min) / (el.max - el.min)) * 100;
  el.style.setProperty("--p", p + "%");
}

/* ---------- persistance locale (dernière séance) ---------- */
function loadSaved() {
  try {
    const s = JSON.parse(localStorage.getItem(LS_KEY) || "null");
    if (s) Object.assign(state, { exercises: s.exercises || [], style: s.style || state.style });
    return s;
  } catch { return null; }
}
function save() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      exercises: state.exercises, style: state.style, hook: $("#hook").value, cta: $("#cta").value, target: +$("#target").value,
    }));
  } catch { /* stockage indisponible : sans conséquence */ }
}

/* ---------- 1. Dépôt ---------- */
const drop = $("#drop"), fileInput = $("#file");
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload([...e.dataTransfer.files]));
fileInput.addEventListener("change", () => upload([...fileInput.files]));

function upload(files) {
  files = files.filter((f) => f.type.startsWith("video/") || /\.(mp4|mov|m4v|mkv|webm|avi|mts)$/i.test(f.name));
  if (!files.length) return toast("Choisis des fichiers vidéo (mp4, mov…)", true);
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f, f.name));
  const prog = $(".drop-progress"), bar = $("#up-bar"), txt = $("#up-text");
  const total = files.reduce((a, f) => a + f.size, 0);
  prog.hidden = false;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/projects");
  xhr.upload.onprogress = (e) => {
    const p = e.lengthComputable ? e.loaded / e.total : 0;
    bar.style.width = (p * 100).toFixed(1) + "%";
    txt.textContent = `Import de ${files.length} fichier${files.length > 1 ? "s" : ""} · ${(total / 1e9).toFixed(2)} Go · ${Math.round(p * 100)}%`;
  };
  xhr.onload = () => {
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch { /* réponse non JSON */ }
    if (xhr.status >= 300) { prog.hidden = true; return toast(data.detail || "Échec de l'import", true); }
    txt.textContent = "Import terminé";
    state.pid = data.id;
    history.replaceState(null, "", "#" + data.id);
    startAnalysis();
  };
  xhr.onerror = () => { prog.hidden = true; toast("Connexion au serveur perdue", true); };
  xhr.send(fd);
}

/* ---------- 2. Analyse ---------- */
async function startAnalysis() {
  setStep(2);
  const sec = show("#s-analysis");
  sec.scrollIntoView({ behavior: "smooth", block: "start" });
  for (;;) {
    let p;
    try { p = await api(`/api/projects/${state.pid}`); } catch (e) { return toast(e.message, true); }
    state.project = p;
    $("#an-pct").textContent = Math.round(p.progress * 100) + "%";
    if (p.status === "error" && !p.sources.length) {
      $("#analyzing").innerHTML = `<div class="warn err">${esc(p.error || "Analyse impossible")}</div>`;
      return;
    }
    if (p.status !== "analyzing") break;
    await sleep(600);
  }
  $("#analyzing").hidden = true;
  renderStats();
  renderTimelines();
  setStep(3);
  show("#s-session");
  initSession();
  refreshPlan();
  if (state.project.result) showResult(state.project);
}

function renderStats() {
  const src = state.project.sources;
  const total = src.reduce((a, s) => a + s.duration, 0);
  const sets = src.flatMap((s) => s.sets);
  const work = sets.reduce((a, s) => a + s.duration, 0);
  $("#stats").innerHTML = [
    [fmt(total), "de rushes"],
    [sets.length, sets.length > 1 ? "séries détectées" : "série détectée"],
    [fmt(work), "d'effort"],
    [total ? Math.round((1 - work / total) * 100) + "%" : "–", "de repos coupé"],
  ].map(([b, s], i) => `<div class="stat" style="animation-delay:${i * 70}ms"><b>${b}</b><span>${s}</span></div>`).join("");
}

function curvePath(values) {
  if (!values.length) return "";
  const n = values.length;
  let d = `M0,100 `;
  values.forEach((v, i) => { d += `L${((i / (n - 1 || 1)) * 1000).toFixed(1)},${(100 - v * 88).toFixed(1)} `; });
  return d + "L1000,100 Z";
}

function renderTimelines() {
  const host = $("#timelines");
  host.innerHTML = "";
  state.project.sources.forEach((src, si) => {
    const el = document.createElement("div");
    el.className = "timeline";
    el.style.animationDelay = si * 80 + "ms";
    const tick = (t) => (src.duration < 20 ? `${t.toFixed(1)} s` : fmt(t));
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => `<span>${tick(f * src.duration)}</span>`).join("");
    el.innerHTML = `
      <div class="tl-head"><span>${esc(src.name)}</span><span class="muted">${src.width}×${src.height} · ${fmt(src.duration)}</span></div>
      <div class="tl-track">
        <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
          <defs><linearGradient id="curveFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="rgba(255,255,255,.28)"/><stop offset="1" stop-color="rgba(255,255,255,0)"/></linearGradient></defs>
          <path class="tl-curve" d="${curvePath(src.curve)}"/>
        </svg>
      </div>
      <div class="tl-axis">${ticks}</div>`;
    host.appendChild(el);
    const track = $(".tl-track", el);
    if (!src.sets.length) {
      track.insertAdjacentHTML("beforeend", `<div class="empty" style="position:absolute;inset:10px;display:grid;place-items:center">Aucune série détectée dans ce fichier</div>`);
    }
    src.sets.forEach((s, k) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tl-set";
      b.dataset.id = s.id;
      b.style.left = (s.start / src.duration) * 100 + "%";
      b.style.width = Math.max(0.6, ((s.end - s.start) / src.duration) * 100) + "%";
      b.style.animationDelay = 150 + k * 50 + "ms";
      const reps = s.reps_est ? ` · ~${s.reps_est} reps` : "";
      b.title = `${fmt(s.start)} → ${fmt(s.end)} (${Math.round(s.duration)} s${reps}) — clic pour exclure/inclure`;
      b.setAttribute("aria-label", b.title);
      b.innerHTML = `<span class="tag"></span>`;
      b.addEventListener("click", () => {
        state.excluded.has(s.id) ? state.excluded.delete(s.id) : state.excluded.add(s.id);
        paintSets();
        refreshPlan();
      });
      track.appendChild(b);
    });
  });
  $("#tl-hint").hidden = false;
  paintSets();
}

function paintSets() {
  const groupOf = {};
  state.groups.forEach((g, gi) => g.forEach((id) => (groupOf[id] = gi)));
  const named = state.exercises.filter((e) => e.name.trim());
  let n = 0;
  document.querySelectorAll(".tl-set").forEach((b) => {
    const id = b.dataset.id, off = state.excluded.has(id);
    b.classList.toggle("off", off);
    const gi = groupOf[id];
    b.style.setProperty("--c", gi === undefined ? "#6b7079" : GROUP_COLORS[gi % GROUP_COLORS.length]);
    const ex = named[gi];
    n++;
    $(".tag", b).textContent = off ? "exclue" : ex && ex.name ? ex.name : `Série ${n}`;
  });
  let k = 0;
  document.querySelectorAll(".ex").forEach((row, i) => {
    const filled = state.exercises[i] && state.exercises[i].name.trim();
    row.style.setProperty("--c", filled ? GROUP_COLORS[k++ % GROUP_COLORS.length] : "transparent");
  });
}

/* ---------- 3. Séance ---------- */
let sessionReady = false;
function initSession() {
  if (sessionReady) return;
  sessionReady = true;
  const saved = loadSaved();
  $("#ex-names").innerHTML = EXERCISES.map((e) => `<option value="${esc(e)}">`).join("");
  if (!state.exercises.length) state.exercises = [{ name: "", sets: "", reps: "", load: "" }];
  if (saved) {
    $("#hook").value = saved.hook || "";
    $("#cta").value = saved.cta || "";
    if (saved.target) $("#target").value = saved.target;
  }
  renderExercises();
  fillChips("hook", HOOKS);
  fillChips("cta", CTAS);
  loadStyles();

  const t = $("#target");
  const onTarget = () => { syncRange(t); $("#target-val").textContent = t.value + " s"; };
  onTarget();
  t.addEventListener("input", () => { onTarget(); refreshPlan(); save(); });
  ["#hook", "#cta"].forEach((id) => $(id).addEventListener("input", () => { refreshPlan(); save(); }));
  $("#add-ex").addEventListener("click", () => {
    state.exercises.push({ name: "", sets: "", reps: "", load: "" });
    renderExercises();
    const rows = document.querySelectorAll(".ex .name");
    rows[rows.length - 1].focus();
  });
  $("#music").addEventListener("change", uploadMusic);
  ["#music-vol"].forEach((id) => { const el = $(id); syncRange(el); el.addEventListener("input", () => syncRange(el)); });
  $("#beat").addEventListener("change", refreshPlan);
  $("#render").addEventListener("click", startRender);
  $("#again").addEventListener("click", () => {
    setStep(3);
    $("#s-session").scrollIntoView({ behavior: "smooth" });
  });
}

function fillChips(target, list) {
  const host = $(`.chips[data-for="${target}"]`);
  host.innerHTML = list.map((t) => `<button type="button" class="chip">${esc(t)}</button>`).join("");
  host.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
    $("#" + target).value = c.textContent;
    refreshPlan();
    save();
  }));
}

function renderExercises() {
  const host = $("#exercises");
  host.innerHTML = `<div class="ex-legend"><span></span><span>Exercice</span><span>Séries</span><span class="reps">Reps</span><span class="load">Charge</span><span></span></div>`;
  state.exercises.forEach((ex, i) => {
    const row = document.createElement("div");
    row.className = "ex";
    row.innerHTML = `
      <span class="dot"></span>
      <input class="input name" list="ex-names" placeholder="Développé couché" value="${esc(ex.name)}" aria-label="Exercice ${i + 1}">
      <input class="input sets" type="number" min="1" max="20" placeholder="4" value="${esc(ex.sets)}" aria-label="Séries">
      <input class="input reps" placeholder="8-10" value="${esc(ex.reps)}" aria-label="Répétitions">
      <input class="input load" placeholder="80 kg" value="${esc(ex.load)}" aria-label="Charge">
      <button class="rm" type="button" aria-label="Supprimer">×</button>`;
    const bind = (cls, key) => $(cls, row).addEventListener("input", (e) => { ex[key] = e.target.value; refreshPlan(); save(); });
    bind(".name", "name"); bind(".sets", "sets"); bind(".reps", "reps"); bind(".load", "load");
    $(".rm", row).addEventListener("click", () => {
      state.exercises.splice(i, 1);
      if (!state.exercises.length) state.exercises.push({ name: "", sets: "", reps: "", load: "" });
      renderExercises();
      refreshPlan();
      save();
    });
    host.appendChild(row);
  });
  paintSets();
}

async function loadStyles() {
  let list = [];
  try { list = await api("/api/styles"); } catch { return; }
  const host = $("#styles");
  host.innerHTML = "";
  const current = list.find((s) => s.key === state.style);
  if (current) $("#labels-note").hidden = current.labels;
  list.forEach((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "style-card" + (s.key === state.style ? " on" : "");
    b.style.setProperty("--sc", "#" + s.accent);
    b.innerHTML = `<span class="sw"></span><b>${esc(s.label)}</b><small>${esc(STYLE_DESC[s.key] || "")}</small>`;
    b.addEventListener("click", () => {
      state.style = s.key;
      host.querySelectorAll(".style-card").forEach((c) => c.classList.toggle("on", c === b));
      const t = $("#target");
      t.value = s.target;
      t.dispatchEvent(new Event("input"));
      $("#labels-note").hidden = s.labels;
      save();
    });
    host.appendChild(b);
  });
}

function payload() {
  return {
    exercises: state.exercises.filter((e) => e.name.trim()).map((e) => ({
      name: e.name.trim(), sets: e.sets ? +e.sets : null, reps: String(e.reps || ""), load: String(e.load || ""),
    })),
    hook: $("#hook").value.trim(),
    cta: $("#cta").value.trim(),
    style: state.style,
    target: +$("#target").value,
    music_start: +$("#music-start").value || 0,
    music_volume: +$("#music-vol").value,
    sync_to_beat: $("#beat").checked,
    excluded: [...state.excluded],
  };
}

const refreshPlan = debounce(async () => {
  if (!state.pid || !state.project || !state.project.sources.length) return;
  const w = $("#plan-warnings");
  try {
    const plan = await jsonPost(`/api/projects/${state.pid}/plan`, payload());
    state.groups = plan.groups;
    $("#estimate").innerHTML = `<div><b>${plan.duration.toFixed(0)} s</b>durée</div><div><b>${plan.clips}</b>plans</div>`;
    w.innerHTML = plan.warnings.map((m) => `<div class="warn">${esc(m)}</div>`).join("");
    $("#render").disabled = false;
  } catch (e) {
    state.groups = [];
    $("#estimate").innerHTML = "";
    w.innerHTML = `<div class="warn err">${esc(e.message)}</div>`;
    $("#render").disabled = true;
  }
  paintSets();
}, 250);

async function uploadMusic() {
  const f = $("#music").files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f, f.name);
  const info = $("#music-info");
  info.hidden = false;
  info.innerHTML = `<span>Analyse du tempo…</span>`;
  try {
    const m = await api(`/api/projects/${state.pid}/music`, { method: "POST", body: fd });
    showMusic(m);
  } catch (e) {
    info.hidden = true;
    toast(e.message, true);
  }
  $("#music").value = "";
}
function showMusic(m) {
  const info = $("#music-info");
  info.hidden = false;
  $("#music-opts").hidden = false;
  info.innerHTML = `<span>♪ ${esc(m.name)}${m.bpm ? ` · <b>${m.bpm} BPM</b>` : ""}</span><button type="button" aria-label="Retirer la musique">×</button>`;
  $("button", info).addEventListener("click", async () => {
    await api(`/api/projects/${state.pid}/music`, { method: "DELETE" }).catch(() => {});
    info.hidden = true;
    $("#music-opts").hidden = true;
    refreshPlan();
  });
  refreshPlan();
}

/* ---------- 4. Rendu ---------- */
async function startRender() {
  const btn = $("#render");
  btn.disabled = true;
  try {
    await jsonPost(`/api/projects/${state.pid}/render`, payload());
  } catch (e) {
    btn.disabled = false;
    return toast(e.message, true);
  }
  setStep(4);
  const sec = show("#s-result");
  $("#result-title").textContent = "Montage en cours";
  $("#rendering").hidden = false;
  $("#video").hidden = true;
  $("#result-side").hidden = true;
  setRing(0);
  sec.scrollIntoView({ behavior: "smooth", block: "start" });
  for (;;) {
    await sleep(500);
    let p;
    try { p = await api(`/api/projects/${state.pid}`); } catch (e) { toast(e.message, true); break; }
    if (p.status === "rendering") { setRing(p.progress); continue; }
    if (p.status === "done") showResult(p);
    else { toast(p.error || "Le rendu a échoué", true); setStep(3); $("#s-result").hidden = true; }
    break;
  }
  btn.disabled = false;
}

function setRing(p) {
  $("#ring").style.strokeDashoffset = (326.7 * (1 - p)).toFixed(1);
  $("#r-pct").textContent = Math.round(p * 100) + "%";
}

function showResult(p) {
  const r = p.result;
  setStep(4);
  show("#s-result");
  $("#result-title").innerHTML = `Vidéo <span class="accent">prête</span>`;
  $("#rendering").hidden = true;
  const v = $("#video");
  v.src = r.video + "?t=" + Date.now();
  v.poster = r.cover + "?t=" + Date.now();
  v.hidden = false;
  v.muted = true;
  v.play().catch(() => {});
  $("#result-side").hidden = false;
  $("#result-meta").textContent = `${r.duration} s · 1080×1920 · 30 i/s · H.264 — format TikTok & Reels.`;
  $("#dl-video").href = r.video;
  $("#dl-video").setAttribute("download", r.path.split(/[\\/]/).pop());
  $("#dl-cover").href = r.cover;
  $("#result-path").textContent = "Enregistrée dans : " + r.path;
  $("#result-warnings").innerHTML = r.warnings.map((m) => `<div class="warn">${esc(m)}</div>`).join("");
}

/* ---------- démarrage ---------- */
setStep(1);
loadSaved();
if (location.hash.length > 1) {
  state.pid = location.hash.slice(1);
  api(`/api/projects/${state.pid}`).then((p) => {
    if (p.music) setTimeout(() => showMusic(p.music), 0);
    startAnalysis();
  }).catch(() => history.replaceState(null, "", "/"));
}
