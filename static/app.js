/* ═══════════════════════════════════════════════════════════════
   LEADHUNTER — Frontend Logic
   ═══════════════════════════════════════════════════════════════ */

const API = "";   // same origin
let currentJobId = null;
let pollTimer = null;
let allLeads = [];
let searchHistory = JSON.parse(localStorage.getItem("lh_history") || "[]");

// ── PARTICLES ────────────────────────────────────────────────────
(function initParticles() {
  const canvas = document.getElementById("particles-canvas");
  const ctx = canvas.getContext("2d");
  let particles = [];

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  function createParticle() {
    return {
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.5 + 0.3,
      dx: (Math.random() - 0.5) * 0.25,
      dy: (Math.random() - 0.5) * 0.25,
      alpha: Math.random() * 0.5 + 0.1,
    };
  }
  for (let i = 0; i < 120; i++) particles.push(createParticle());

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(124,58,237,${p.alpha})`;
      ctx.fill();
      p.x += p.dx;
      p.y += p.dy;
      if (p.x < 0 || p.x > canvas.width)  p.dx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.dy *= -1;
    });

    // Draw faint lines between close particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 100) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(124,58,237,${0.06 * (1 - dist / 100)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(draw);
  }
  draw();
})();

// ── QUICK EXAMPLES ───────────────────────────────────────────────
function fillExample(keyword, location) {
  document.getElementById("keyword-input").value = keyword;
  document.getElementById("location-input").value = location;
  document.getElementById("keyword-input").focus();
}

// ── START SEARCH ─────────────────────────────────────────────────
async function startSearch() {
  const keyword  = document.getElementById("keyword-input").value.trim();
  const location = document.getElementById("location-input").value.trim();
  const maxRes   = parseInt(document.getElementById("max-results-input").value) || 20;

  if (!keyword)  { shake("keyword-input");  return; }
  if (!location) { shake("location-input"); return; }

  // UI state: show progress
  hide("error-section");
  hide("results-section");
  show("progress-section");
  setProgress(5, `Buscando "${keyword}" em ${location}…`, "Abrindo Google Maps…");
  document.getElementById("btn-search").disabled = true;

  try {
    const res = await fetch(`${API}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, location, max_results: maxRes }),
    });
    const data = await res.json();
    currentJobId = data.job_id;
    pollStatus(keyword, location);
  } catch (e) {
    showError("Não foi possível conectar ao servidor. Verifique se o app.py está rodando.");
    document.getElementById("btn-search").disabled = false;
  }
}

// ── POLL STATUS ──────────────────────────────────────────────────
function pollStatus(keyword, location) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res  = await fetch(`${API}/api/status/${currentJobId}`);
      const data = await res.json();

      setProgress(
        data.progress,
        data.message,
        `Leads coletados: ${data.total}`
      );

      if (data.status === "done") {
        clearInterval(pollTimer);
        allLeads = data.results;
        saveHistory(keyword, location, data.total, currentJobId);
        showResults(allLeads);
        hide("progress-section");
        document.getElementById("btn-search").disabled = false;
      } else if (data.status === "error") {
        clearInterval(pollTimer);
        hide("progress-section");
        showError(data.message);
        document.getElementById("btn-search").disabled = false;
      }
    } catch (e) {
      clearInterval(pollTimer);
      showError("Erro ao verificar status da busca.");
      document.getElementById("btn-search").disabled = false;
    }
  }, 1500);
}

// ── SHOW RESULTS ─────────────────────────────────────────────────
function showResults(leads) {
  show("results-section");
  document.getElementById("results-count-badge").textContent = leads.length;
  renderLeads(leads);
  document.getElementById("results-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderLeads(leads) {
  const grid = document.getElementById("leads-grid");
  grid.innerHTML = "";

  if (leads.length === 0) {
    grid.innerHTML = `<div class="lead-empty-state">Nenhum resultado encontrado.</div>`;
    return;
  }

  leads.forEach((lead, i) => {
    const phones = getLeadPhones(lead);
    const websites = getLeadWebsites(lead);
    const mapsUrl = lead.google_maps_url || "";
    const rating = lead.avaliacao ? `${lead.avaliacao}` : "—";
    const reviews = lead.total_avaliacoes ? `(${lead.total_avaliacoes})` : "—";

    const card = document.createElement("article");
    card.className = "lead-card fadeInUp";
    card.style.animationDelay = `${i * 35}ms`;
    card.innerHTML = `
      <div class="lead-card-top">
        <div>
          <div class="lead-card-index">#${lead.posicao || i + 1}</div>
          <h3 class="lead-card-title">${escHtml(lead.nome) || "Lead sem nome"}</h3>
          <div class="lead-card-category">${escHtml(lead.categoria) || "Categoria não informada"}</div>
        </div>
      </div>
      <div class="lead-card-metrics">
        <div class="lead-metric">
          <span class="lead-metric-label">Avaliação</span>
          <span class="lead-metric-value">⭐ ${rating}</span>
        </div>
        <div class="lead-metric">
          <span class="lead-metric-label">Avaliações</span>
          <span class="lead-metric-value">${reviews}</span>
        </div>
        <div class="lead-metric">
          <span class="lead-metric-label">Telefones</span>
          <span class="lead-metric-value">${phones.length || 0}</span>
        </div>
        <div class="lead-metric">
          <span class="lead-metric-label">Redes/Sites</span>
          <span class="lead-metric-value">${websites.length || 0}</span>
        </div>
      </div>
      <div class="lead-card-section">
        <span class="lead-card-section-label">Endereço</span>
        <p class="lead-card-text">${escHtml(lead.endereco) || "—"}</p>
      </div>
      <div class="lead-card-preview-grid">
        <div class="lead-card-preview">
          <span class="lead-card-section-label">Contatos</span>
          <div class="lead-card-chips">${renderChipList(phones, true)}</div>
        </div>
        <div class="lead-card-preview">
          <span class="lead-card-section-label">Redes e sites</span>
          <div class="lead-card-chips">${renderChipList(websites, false)}</div>
        </div>
      </div>
      <div class="lead-card-footer" style="display: flex; gap: 8px; justify-content: flex-end; align-items: center;">
        <button class="lead-card-button" type="button">Ver detalhes</button>
        ${mapsUrl ? `<a class="lead-card-link" href="${mapsUrl}" target="_blank" rel="noopener">Abrir no Maps</a>` : `<span class="tag-empty">Sem link do Maps</span>`}
      </div>
    `;

    card.querySelector(".lead-card-button").addEventListener("click", () => openLeadModal(lead, i));
    card.addEventListener("dblclick", () => openLeadModal(lead, i));
    grid.appendChild(card);
  });
}

function getLeadPhones(lead) {
  const phones = [];
  const sources = [];

  if (Array.isArray(lead.telefones)) sources.push(...lead.telefones);
  if (Array.isArray(lead.phones)) sources.push(...lead.phones);
  if (lead.telefone) sources.push(lead.telefone);

  sources.forEach(item => {
    const value = String(item || "").trim();
    if (value && !phones.includes(value)) phones.push(value);
  });

  return phones;
}

function getLeadWebsites(lead) {
  const websites = [];
  const sources = [];

  if (Array.isArray(lead.websites)) sources.push(...lead.websites);
  if (Array.isArray(lead.socials)) sources.push(...lead.socials);
  if (lead.website) sources.push(lead.website);

  sources.forEach(item => {
    const value = String(item || "").trim();
    if (value && !websites.includes(value)) websites.push(value);
  });

  return websites;
}

function renderChipList(items, isPhone) {
  if (!items.length) return `<span class="tag-empty">—</span>`;
  return items
    .slice(0, 3)
    .map(item => {
      const label = truncate(item.replace(/^https?:\/\//, ""), 28);
      const href = isPhone ? `tel:${item.replace(/\D/g, "")}` : item;
      const target = isPhone ? "" : 'target="_blank" rel="noopener"';
      return `<a class="lead-chip" href="${href}" ${target}>${escHtml(label)}</a>`;
    })
    .join("");
}

function openLeadModal(lead, index) {
  const phones = getLeadPhones(lead);
  const websites = getLeadWebsites(lead);
  const modalBackdrop = document.getElementById("lead-modal-backdrop");

  document.getElementById("lead-modal-index").textContent = `Lead ${String(index + 1).padStart(2, "0")}`;
  document.getElementById("lead-modal-title").textContent = lead.nome || "Lead sem nome";
  document.getElementById("lead-modal-category").textContent = lead.categoria || "Categoria não informada";
  document.getElementById("lead-modal-rating").textContent = lead.avaliacao || "—";
  document.getElementById("lead-modal-reviews").textContent = lead.total_avaliacoes ? `${lead.total_avaliacoes}` : "—";
  document.getElementById("lead-modal-contacts-count").textContent = `${phones.length} telefone(s) · ${websites.length} link(s)`;
  document.getElementById("lead-modal-address").textContent = lead.endereco || "—";
  document.getElementById("lead-modal-phones").innerHTML = phones.length
    ? phones.map(phone => `<a class="lead-detail-link" href="tel:${phone.replace(/\D/g, "")}">${escHtml(phone)}</a>`).join("")
    : `<span class="tag-empty">Nenhum telefone encontrado.</span>`;
  document.getElementById("lead-modal-websites").innerHTML = websites.length
    ? websites.map(site => `<a class="lead-detail-link" href="${site}" target="_blank" rel="noopener">${escHtml(truncate(site.replace(/^https?:\/\//, ""), 50))}</a>`).join("")
    : `<span class="tag-empty">Nenhum site ou rede social encontrado.</span>`;

  const mapsUrl = lead.google_maps_url || "#";
  const mapsLink = document.getElementById("lead-modal-maps-link");
  mapsLink.href = mapsUrl;
  mapsLink.style.pointerEvents = mapsUrl === "#" ? "none" : "";
  mapsLink.style.opacity = mapsUrl === "#" ? "0.5" : "1";

  modalBackdrop.style.display = "flex";
  document.body.classList.add("modal-open");
}

function closeLeadModal(event) {
  if (event && event.target !== event.currentTarget) return;
  const modalBackdrop = document.getElementById("lead-modal-backdrop");
  modalBackdrop.style.display = "none";
  document.body.classList.remove("modal-open");
}

// ── FILTER ───────────────────────────────────────────────────────
function filterResults() {
  const q = document.getElementById("filter-input").value.toLowerCase();
  if (!q) {
    document.getElementById("results-count-badge").textContent = allLeads.length;
    renderLeads(allLeads);
    return;
  }
  const filtered = allLeads.filter(l => {
    const phones = getLeadPhones(l).join(" ");
    const websites = getLeadWebsites(l).join(" ");
    return (
      (l.nome      || "").toLowerCase().includes(q) ||
      (l.categoria || "").toLowerCase().includes(q) ||
      (l.endereco  || "").toLowerCase().includes(q) ||
      phones.toLowerCase().includes(q) ||
      websites.toLowerCase().includes(q)
    );
  });
  document.getElementById("results-count-badge").textContent = filtered.length;
  renderLeads(filtered);
}

// ── EXPORT EXCEL ─────────────────────────────────────────────────
async function exportExcel() {
  if (!currentJobId) return;
  window.open(`${API}/api/export/${currentJobId}`, "_blank");
}

// ── EXPORT PDF ──────────────────────────────────────────────────
async function exportPdf() {
  if (!currentJobId) return;
  window.open(`${API}/api/export-pdf/${currentJobId}`, "_blank");
}

// ── RESET ─────────────────────────────────────────────────────────
function resetSearch() {
  hide("results-section");
  hide("progress-section");
  hide("error-section");
  closeLeadModal();
  show("hero");
  document.getElementById("btn-search").disabled = false;
  currentJobId = null;
  allLeads = [];
  clearInterval(pollTimer);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ── HISTORY ──────────────────────────────────────────────────────
function saveHistory(keyword, location, total, jobId) {
  const entry = {
    keyword, location, total, jobId,
    date: new Date().toLocaleString("pt-BR"),
  };
  searchHistory.unshift(entry);
  if (searchHistory.length > 10) searchHistory.pop();
  localStorage.setItem("lh_history", JSON.stringify(searchHistory));
  renderHistory();
}

function clearSearchHistory() {
  if (!searchHistory.length) return;
  const confirmed = window.confirm("Deseja limpar todas as buscas recentes?");
  if (!confirmed) return;
  searchHistory = [];
  localStorage.removeItem("lh_history");
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById("history-list");
  if (!searchHistory.length) {
    list.innerHTML = `<div class="history-empty">Nenhuma busca realizada ainda.</div>`;
    return;
  }
  list.innerHTML = searchHistory.map((h, i) => `
    <div class="history-item" onclick="loadHistoryJob('${h.jobId}', '${escAttr(h.keyword)}', '${escAttr(h.location)}')">
      <span class="history-item-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="ui-icon" role="img" aria-hidden="true">
          <rect x="6" y="4" width="12" height="16" rx="2" />
          <path d="M9 4.5V3h6v1.5" />
          <path d="M9 9h6M9 13h6M9 17h4" />
        </svg>
      </span>
      <div class="history-item-info">
        <div class="history-item-query">${escHtml(h.keyword)} em ${escHtml(h.location)}</div>
        <div class="history-item-meta">${h.date}</div>
      </div>
      <span class="history-item-count">${h.total} leads</span>
    </div>
  `).join("");
}

async function loadHistoryJob(jobId, keyword, location) {
  try {
    const res  = await fetch(`${API}/api/results/${jobId}`);
    const data = await res.json();
    if (data.results && data.results.length) {
      currentJobId = jobId;
      allLeads = data.results;
      document.getElementById("keyword-input").value  = keyword;
      document.getElementById("location-input").value = location;
      showResults(allLeads);
    }
  } catch (e) {
    alert("Resultados desta busca já não estão disponíveis (servidor reiniciado).");
  }
}

// ── HELPERS ──────────────────────────────────────────────────────
function setProgress(pct, title, subtitle) {
  document.getElementById("progress-bar-fill").style.width = pct + "%";
  document.getElementById("progress-pct").textContent = pct + "%";
  document.getElementById("progress-title").textContent = title;
  document.getElementById("progress-subtitle").textContent = subtitle;
  document.getElementById("progress-found").textContent = subtitle;
}

function show(id) {
  const el = document.getElementById(id);
  if (el) { el.style.display = ""; el.classList.add("fadeInUp"); }
}
function hide(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = "none";
}
function showError(msg) {
  show("error-section");
  document.getElementById("error-message").textContent = msg;
}
function shake(id) {
  const el = document.getElementById(id);
  el.style.animation = "none";
  el.offsetHeight; // reflow
  el.style.animation = "shake 0.4s ease";
  el.focus();
}
function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + "…" : str;
}
function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function escAttr(str) {
  return String(str || "").replace(/'/g, "\\'");
}

// ── KEYBOARD SHORTCUT ────────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    const active = document.activeElement;
    if (
      active?.id === "keyword-input" ||
      active?.id === "location-input" ||
      active?.id === "max-results-input"
    ) {
      startSearch();
    }
  }
  if (e.key === "Escape") {
    closeLeadModal();
  }
});

// ── SHAKE ANIMATION ──────────────────────────────────────────────
const shakeStyle = document.createElement("style");
shakeStyle.textContent = `
@keyframes shake {
  0%,100% { transform: translateX(0); }
  20% { transform: translateX(-6px); }
  40% { transform: translateX(6px); }
  60% { transform: translateX(-4px); }
  80% { transform: translateX(4px); }
}`;
document.head.appendChild(shakeStyle);

// ── INIT ─────────────────────────────────────────────────────────
renderHistory();
