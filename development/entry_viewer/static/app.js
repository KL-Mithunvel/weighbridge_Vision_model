"use strict";

// Weighment entry viewer — vanilla JS, talks only to the local Flask API.
const VOCAB = window.VOCAB;
const $ = (id) => document.getElementById(id);

const state = {
  entry: null,      // /api/entries/<serial> payload
  photos: [],       // flat list across visits, for lightbox navigation
  lbIndex: -1,
};

// ------------------------------------------------------------------ helpers
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error(body?.error || `${res.status} ${res.statusText}`);
  return body;
}

function postJson(path, payload) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function showStatus(message, isError = false) {
  const el = $("status");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = !message;
}

// An <img> error hides the server's JSON message; re-request it to surface it.
async function reportImageError(url) {
  try {
    const res = await fetch(url);
    const body = await res.json();
    showStatus(`Image failed: ${body.error || res.status}`, true);
  } catch {
    showStatus("Image failed to load (see the server console).", true);
  }
}

function labeller() {
  return $("labeller").value.trim();
}

function timeOf(iso) {
  return iso ? iso.slice(11, 19) : "no time";
}

function mb(bytes) {
  return (bytes / 1048576).toFixed(2) + " MB";
}

function parseList(value) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [String(parsed)];
  } catch {
    return [String(value)];
  }
}

// ------------------------------------------------------------ date / entry
async function loadDates() {
  const dates = await api("/api/dates");
  $("date-select").innerHTML = dates.map((d) => {
    const flags = [];
    if (d.without_images) flags.push(`${d.without_images} without photos`);
    if (d.without_report) flags.push(`${d.without_report} without report`);
    return `<option value="${d.date}">${d.date} · ${d.entries} entries · ${d.photos} photos${flags.length ? " · ⚠ " + flags.join(", ") : ""}</option>`;
  }).join("");
  return dates;
}

async function loadEntries(date, selectSerial) {
  $("date-select").value = date;
  const rows = await api(`/api/dates/${date}/entries`);
  $("entry-select").innerHTML = rows.map((r) => {
    const bits = [
      r.photos ? `${r.photos} photos` : "⚠ NO PHOTOS (SQL only)",
      r.reports ? `report${r.reports > 1 ? " ×" + r.reports : ""} ✓` : "⚠ NO REPORT (AWS only)",
    ];
    if (r.duplicate_folders) bits.push("⚠ dup folders");
    if (r.labelled) bits.push("labelled ✓");
    return `<option value="${r.serial}">${r.number} · ${bits.join(" · ")}</option>`;
  }).join("");
  const target = selectSerial && rows.some((r) => r.serial === selectSerial)
    ? selectSerial : rows[0]?.serial;
  if (target) await loadEntry(target);
}

async function loadEntry(serial) {
  showStatus("");
  $("entry-select").value = serial;
  history.replaceState(null, "", `#${serial}`);
  const entry = await api(`/api/entries/${serial}`);
  state.entry = entry;
  state.photos = entry.visits.flatMap((v) => v.photos);
  $("prev-btn").disabled = !entry.prev;
  $("next-btn").disabled = !entry.next;
  renderPhotos(entry);
  renderReport(entry.reports);
  renderEntryLabels(entry);
}

// ----------------------------------------------------------------- photos
function roleBadge(photo) {
  if (photo.label?.role) return `<span class="badge solid">${esc(photo.label.role)}</span>`;
  return `<span class="badge guess" title="Provisional guess from ${photo.resolution ? "resolution" : "file size"}">${esc(photo.role_guess)}?</span>`;
}

function renderPhotos(entry) {
  const host = $("photos");
  const head = `<div class="entry-head">
      <strong>${esc(entry.serial)}</strong>
      <span class="muted">${esc(entry.date)} · folder${entry.folders.length > 1 ? "s" : ""}: ${entry.folders.map(esc).join(", ") || "—"}</span>
      ${entry.folders.length > 1 ? '<span class="badge warn">stored under both folder conventions — may contain duplicates</span>' : ""}
    </div>`;
  const noReport = !entry.reports.length
    ? `<div class="notice warn"><strong>No SQL report for this entry.</strong>
        The photos are in the S3 archive but the LLM audit system never produced a report for this serial
        (its transaction numbers skip here). Nothing is wrong with the photos.</div>` : "";
  if (!state.photos.length) {
    host.innerHTML = head + `<div class="notice warn"><strong>No photos for this entry.</strong>
        This serial has an SQL report but nothing in the S3 archive. All such entries are from
        2026-08-06 onward — the archive's last photos are from 2026-08-05, while reports continue to 2026-08-26.
        The report is still shown on the right; it describes photos we cannot see. Ask the bucket admin whether
        the August photos exist elsewhere.</div>`;
    return;
  }
  let flat = 0;
  host.innerHTML = head + noReport + entry.visits.map((visit) => {
    const first = visit.photos[0], last = visit.photos[visit.photos.length - 1];
    const tiles = visit.photos.map((p) => {
      const i = flat++;
      return `<figure class="tile ${p.label ? "labelled" : ""}" data-index="${i}">
          <img loading="lazy" src="/api/photo/thumb?key=${encodeURIComponent(p.key)}" alt="">
          <figcaption>
            ${roleBadge(p)}
            <span>${timeOf(p.captured_at)}</span>
            <span class="muted">${p.resolution || mb(p.size)}</span>
            ${p.cached ? "" : '<span class="muted" title="Not cached yet — first view downloads from S3 (GLACIER_IR retrieval)">☁</span>'}
          </figcaption>
        </figure>`;
    }).join("");
    return `<div class="visit">
        <h3>${esc(visit.caption)} <span class="muted small">${timeOf(first.captured_at)}–${timeOf(last.captured_at)} · ${visit.photos.length} photos</span></h3>
        <div class="grid">${tiles}</div>
      </div>`;
  }).join("");
  host.querySelectorAll(".tile").forEach((tile) =>
    tile.addEventListener("click", () => openLightbox(Number(tile.dataset.index))));
  host.querySelectorAll(".tile img").forEach((img) =>
    img.addEventListener("error", () => {
      img.closest(".tile").classList.add("broken");
      reportImageError(img.src);
    }));
}

// ----------------------------------------------------------------- report
const HELP = {
  created: "When the LLM audit report was generated (IST), and the weighment transaction id.",
  plate: "Vehicle number plate as read from the photos by the LLM. The tick says whether it matched the declared vehicle.",
  weight: "Did the LLM judge the declared weight plausible for the load it saw?",
  consistency: "The LLM's own overall confidence (0-1) that everything agrees. Not ground truth.",
  load: "Free-text description of the load the LLM saw.",
  tampering: "Free-text list of anything suspicious the LLM noticed. Not a fixed category list.",
  flags: "Short warning tags raised by the LLM.",
  summary: "One-paragraph verdict.",
  feedback: "Extra remarks the LLM added, often about missing or unreadable evidence.",
};
const tip = (k) => `title="${esc(HELP[k])}"`;

const BOOL = (v) => v === 1 ? '<span class="ok">✓ yes</span>' : v === 0 ? '<span class="bad">✗ no</span>' : '<span class="muted">—</span>';

function renderReport(reports) {
  const host = $("report");
  if (!reports.length) {
    host.innerHTML = '<p class="muted">No SQL report for this serial.</p>';
    return;
  }
  const tabs = reports.length > 1
    ? `<div class="tabs">${reports.map((r, i) => `<button data-i="${i}" class="${i ? "" : "active"}">${esc(r.created_at)}</button>`).join("")}</div>`
    : "";
  host.innerHTML = tabs + '<div id="report-body"></div>';
  const show = (i) => {
    const r = reports[i];
    const score = r.consistency_score;
    const list = (v) => {
      const items = parseList(v);
      return items.length ? `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : '<span class="muted">none</span>';
    };
    $("report-body").innerHTML = `
      <dl class="report">
        <dt ${tip('created')}>created</dt><dd>${esc(r.created_at)} · txn ${esc(r.transaction_id)}</dd>
        <dt ${tip('plate')}>plate (OCR)</dt><dd><code>${esc(r.plate_ocr) || "—"}</code> ${BOOL(r.plate_match)}</dd>
        <dt ${tip('weight')}>weight plausible</dt><dd>${BOOL(r.weight_plausible)}</dd>
        <dt ${tip('consistency')}>consistency</dt><dd>${score == null ? "—" : `<span class="meter"><span style="width:${Math.round(score * 100)}%"></span></span> ${score.toFixed(2)}`}</dd>
        <dt ${tip('load')}>load</dt><dd>${esc(r.load_assessment)}</dd>
        <dt ${tip('tampering')}>tampering</dt><dd>${list(r.tampering_signs)}</dd>
        <dt ${tip('flags')}>flags</dt><dd>${list(r.flags)}</dd>
        <dt ${tip('summary')}>summary</dt><dd>${esc(r.summary)}</dd>
        <dt ${tip('feedback')}>feedback</dt><dd>${esc(r.feedback) || '<span class="muted">—</span>'}</dd>
      </dl>`;
    host.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", Number(b.dataset.i) === i));
  };
  host.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(Number(b.dataset.i))));
  show(0);
}

// ----------------------------------------------------------------- labels
function renderChips(host, vocab, current, onPick) {
  host.innerHTML = Object.entries(vocab).map(([field, choices]) => `
    <div class="field"><span class="field-name">${esc(field.replaceAll("_", " "))}</span>
      ${choices.map((c) => `<button class="chip ${current?.[field] === c ? "on" : ""}" data-field="${field}" data-value="${esc(c)}">${esc(c)}</button>`).join("")}
    </div>`).join("");
  host.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
    const { field, value } = chip.dataset;
    onPick(field, current?.[field] === value ? null : value);
  }));
}

function fieldsFrom(vocab, label, notes) {
  const fields = {};
  for (const f of Object.keys(vocab)) fields[f] = label?.[f] ?? null;
  fields.notes = notes;
  return fields;
}

function savedText(label) {
  return label ? `saved ${esc(label.updated_at)}${label.labeller ? " by " + esc(label.labeller) : ""}` : "not labelled";
}

function renderEntryLabels(entry) {
  const label = entry.entry_label;
  renderChips($("entry-label-form"), VOCAB.entry, label, (field, value) =>
    saveEntryLabel({ ...label, [field]: value }));
  $("entry-notes").value = label?.notes || "";
  $("entry-saved").innerHTML = savedText(label);
}

async function saveEntryLabel(label) {
  const entry = state.entry;
  try {
    const fields = fieldsFrom(VOCAB.entry, label, $("entry-notes").value);
    const res = await postJson("/api/labels/entry", { serial: entry.serial, labeller: labeller(), fields });
    entry.entry_label = res.cleared ? null : { ...fields, labeller: labeller(), updated_at: res.updated_at };
    renderEntryLabels(entry);
  } catch (err) {
    showStatus(`Entry label not saved: ${err.message}`, true);
  }
}

async function savePhotoLabel(photo, label) {
  try {
    const fields = fieldsFrom(VOCAB.photo, label, $("photo-notes").value);
    const res = await postJson("/api/labels/photo", { key: photo.key, labeller: labeller(), fields });
    photo.label = res.cleared ? null : { ...fields, labeller: labeller(), updated_at: res.updated_at };
    renderLightboxPanel();
    renderPhotos(state.entry);
  } catch (err) {
    showStatus(`Photo label not saved: ${err.message}`, true);
  }
}

// --------------------------------------------------------------- lightbox
function openLightbox(i) {
  state.lbIndex = i;
  $("lightbox").hidden = false;
  const photo = state.photos[i];
  const img = $("lb-img");
  $("lb-loading").hidden = false;
  $("lb-loading").textContent = "fetching original from S3…";
  img.onload = () => { $("lb-loading").hidden = true; };
  img.onerror = () => {
    $("lb-loading").textContent = "could not load original — see status bar";
    reportImageError(img.src);
  };
  img.src = `/api/photo/full?key=${encodeURIComponent(photo.key)}`;
  renderLightboxPanel();
}

function renderLightboxPanel() {
  const photo = state.photos[state.lbIndex];
  if (!photo) return;
  const visit = state.entry.visits.find((v) => v.photos.includes(photo));
  $("lb-title").textContent = `${state.lbIndex + 1}/${state.photos.length} · ${timeOf(photo.captured_at)}`;
  $("lb-meta").innerHTML = `${esc(visit.caption)}<br>${esc(photo.key)}<br>
    ${photo.resolution || "resolution unknown"} · ${mb(photo.size)} · role guess <em>${esc(photo.role_guess)}</em> (provisional)`;
  renderChips($("photo-label-form"), VOCAB.photo, photo.label, (field, value) =>
    savePhotoLabel(photo, { ...photo.label, [field]: value }));
  $("photo-notes").value = photo.label?.notes || "";
  $("photo-saved").innerHTML = savedText(photo.label);
}

function closeLightbox() {
  $("lightbox").hidden = true;
  $("lb-img").removeAttribute("src");
  state.lbIndex = -1;
}

function stepLightbox(delta) {
  const next = state.lbIndex + delta;
  if (next >= 0 && next < state.photos.length) openLightbox(next);
}

// ----------------------------------------------------------------- wiring
function wire() {
  $("date-select").addEventListener("change", (e) => loadEntries(e.target.value).catch(fail));
  $("entry-select").addEventListener("change", (e) => loadEntry(e.target.value).catch(fail));
  $("prev-btn").addEventListener("click", () => state.entry?.prev && loadEntry(state.entry.prev).catch(fail));
  $("next-btn").addEventListener("click", () => state.entry?.next && loadEntry(state.entry.next).catch(fail));
  $("coverage-btn").addEventListener("click", () => showCoverage().catch(fail));
  $("coverage-close").addEventListener("click", () => { $("coverage").hidden = true; });
  $("lb-close").addEventListener("click", closeLightbox);
  $("lb-prev").addEventListener("click", () => stepLightbox(-1));
  $("lb-next").addEventListener("click", () => stepLightbox(1));
  $("photo-notes").addEventListener("change", () => {
    const photo = state.photos[state.lbIndex];
    if (photo) savePhotoLabel(photo, photo.label);
  });
  $("entry-notes").addEventListener("change", () => state.entry && saveEntryLabel(state.entry.entry_label));

  try { $("labeller").value = localStorage.getItem("labeller") || ""; } catch { /* storage blocked */ }
  $("labeller").addEventListener("change", () => {
    try { localStorage.setItem("labeller", labeller()); } catch { /* storage blocked */ }
  });

  $("refresh-btn").addEventListener("click", async () => {
    showStatus("Re-listing the S3 bucket…");
    try {
      const res = await postJson("/api/refresh", {});
      showStatus(`Refreshed: ${res.objects} objects, ${res.entries} entries.`);
      await loadDates();
      if (state.entry) await loadEntries(state.entry.date, state.entry.serial);
    } catch (err) { fail(err); }
  });

  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (!$("lightbox").hidden) {
      if (e.key === "Escape") closeLightbox();
      else if (e.key === "ArrowLeft") stepLightbox(-1);
      else if (e.key === "ArrowRight") stepLightbox(1);
    } else if (e.key === "," && state.entry?.prev) loadEntry(state.entry.prev).catch(fail);
    else if (e.key === "." && state.entry?.next) loadEntry(state.entry.next).catch(fail);
  });
}

// ----------------------------------------------------------------- coverage
async function showCoverage() {
  const cov = await api("/api/coverage");
  const group = (title, note, serials) => `
    <div><h3>${title} — ${serials.length}</h3><div class="muted small">${note}</div>
      <div class="serial-list">${serials.map((s) => `<button data-serial="${s}">${s}</button>`).join("") || '<span class="muted">none</span>'}</div></div>`;
  $("coverage-body").innerHTML = `<div class="cols">
      ${group("In both", "photos in S3 and a SQL report", cov.both)}
      ${group("AWS only", "photos but no SQL report", cov.aws_only)}
      ${group("SQL only", "SQL report but no photos in S3", cov.sql_only)}
    </div>`;
  $("coverage").hidden = false;
  $("coverage-body").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const serial = b.dataset.serial;
    const date = `${serial.slice(0, 4)}-${serial.slice(4, 6)}-${serial.slice(6, 8)}`;
    loadEntries(date, serial).catch(fail);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));
}

function fail(err) {
  showStatus(err.message, true);
}

async function init() {
  wire();
  try {
    const dates = await loadDates();
    const hashSerial = location.hash.slice(1);
    const fromHash = /^\d{8}-\d{3}$/.test(hashSerial)
      ? `${hashSerial.slice(0, 4)}-${hashSerial.slice(4, 6)}-${hashSerial.slice(6, 8)}` : null;
    const date = dates.some((d) => d.date === fromHash) ? fromHash : dates[0]?.date;
    if (date) await loadEntries(date, hashSerial);
  } catch (err) { fail(err); }
}

init();
