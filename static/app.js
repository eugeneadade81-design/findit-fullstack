const state = {
  user: null,
  listings: [],
  currentListing: null,
  deferredPrompt: null,
  myListings: [],
  myClaims: [],
};

const qs = (selector) => document.querySelector(selector);

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadSession();
  await loadListings();
  registerPwa();
});

function bindEvents() {
  qs("#open-auth").addEventListener("click", () => qs("#auth-dialog").showModal());
  qs("#close-auth").addEventListener("click", () => qs("#auth-dialog").close());
  qs("#logout-button").addEventListener("click", logout);
  qs("#login-form").addEventListener("submit", submitLogin);
  qs("#register-form").addEventListener("submit", submitRegister);
  qs("#report-form").addEventListener("submit", submitReport);
  qs("#claim-form").addEventListener("submit", submitClaim);
  qs("#cancel-edit").addEventListener("click", resetReportForm);
  qs("#search-input").addEventListener("input", renderListings);
  qs("#filter-type").addEventListener("change", renderListings);
  qs("#filter-status").addEventListener("change", renderListings);
  qs("#filter-category").addEventListener("change", renderListings);
  qs("#install-app").addEventListener("click", installApp);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

async function loadSession() {
  const data = await api("/api/session");
  state.user = data.user;
  applySessionUi();
}

function applySessionUi() {
  const guest = !state.user;
  qs("#session-title").textContent = guest ? "Browse as a guest" : `Welcome, ${state.user.fullName}`;
  qs("#session-copy").textContent = guest
    ? "Create an account or sign in to report items, submit claims, and access your dashboard."
    : `${state.user.role === "admin" ? "Admin access enabled." : "Student access enabled."} You can now manage reports, claims, and listing details.`;
  qs("#open-auth").classList.toggle("hidden", !guest);
  qs("#logout-button").classList.toggle("hidden", guest);
  qs("#dashboard").classList.toggle("hidden", guest);
  qs("#admin-section").classList.toggle("hidden", !(state.user && state.user.role === "admin"));
  qs("#profile-card").innerHTML = guest ? "" : `
    ${stackItem("Full name", state.user.fullName)}
    ${stackItem("Email", state.user.email)}
    ${stackItem("Role", capitalize(state.user.role))}
    ${stackItem("Faculty", state.user.faculty || "Not set")}
  `;

  if (guest) {
    qs("#my-listings").innerHTML = `<div class="stack-item"><span>Sign in to manage your reports.</span><strong>-</strong></div>`;
    qs("#my-claims").innerHTML = `<div class="stack-item"><span>Your claims will appear here after sign-in.</span><strong>-</strong></div>`;
  } else {
    loadMyData();
  }

  if (state.user && state.user.role === "admin") {
    loadAnalytics();
  }
}

async function loadListings() {
  const data = await api("/api/listings");
  state.listings = data.listings;
  populateCategoryFilter();
  renderHeroMetrics();
  renderListings();
}

async function loadMyData() {
  try {
    const [myListings, myClaims] = await Promise.all([
      api("/api/my/listings"),
      api("/api/my/claims")
    ]);
    state.myListings = myListings.listings;
    state.myClaims = myClaims.claims;
    renderMySections();
  } catch {
    qs("#my-listings").innerHTML = `<div class="stack-item"><span>Could not load your reports.</span><strong>-</strong></div>`;
    qs("#my-claims").innerHTML = `<div class="stack-item"><span>Could not load your claims.</span><strong>-</strong></div>`;
  }
}

function renderMySections() {
  qs("#my-listings").innerHTML = state.myListings.length
    ? state.myListings.map((item) => `
        <div class="stack-item">
          <span>${escapeHtml(item.itemName)} • ${capitalize(item.status)}</span>
          <strong class="inline-actions">
            <button class="mini-link" type="button" onclick="openDetail(${item.id})">Open</button>
            <button class="mini-link" type="button" onclick="prefillEdit(${item.id})">Edit</button>
          </strong>
        </div>
      `).join("")
    : `<div class="stack-item"><span>No reports created yet.</span><strong>0</strong></div>`;

  qs("#my-claims").innerHTML = state.myClaims.length
    ? state.myClaims.map((claim) => `
        <div class="stack-item">
          <span>${escapeHtml(claim.itemName)} • ${capitalize(claim.status)}</span>
          <strong class="inline-actions">
            <button class="mini-link" type="button" onclick="openDetail(${claim.listingId})">View</button>
          </strong>
        </div>
      `).join("")
    : `<div class="stack-item"><span>No claims submitted yet.</span><strong>0</strong></div>`;
}

function renderHeroMetrics() {
  const metrics = summarize(state.listings);
  qs("#hero-metrics").innerHTML = [
    metricCard(metrics.total, "Reports"),
    metricCard(metrics.found, "Found posts"),
    metricCard(metrics.claimed, "Claimed"),
    metricCard(metrics.resolved, "Resolved")
  ].join("");
  qs("#summary-stats").innerHTML = [
    stackItem("Open reports", metrics.open),
    stackItem("Claim activity", metrics.pendingClaims),
    stackItem("Recovery rate", `${metrics.total ? Math.round((metrics.resolved / metrics.total) * 100) : 0}%`)
  ].join("");
}

function populateCategoryFilter() {
  const select = qs("#filter-category");
  const current = select.value || "all";
  const categories = [...new Set(state.listings.map((item) => item.category))].sort();
  select.innerHTML = `<option value="all">All categories</option>` + categories.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
  select.value = categories.includes(current) ? current : "all";
}

function renderListings() {
  const search = qs("#search-input").value.trim().toLowerCase();
  const type = qs("#filter-type").value;
  const status = qs("#filter-status").value;
  const category = qs("#filter-category").value;
  const filtered = state.listings.filter((item) => {
    const haystack = `${item.itemName} ${item.location} ${item.description} ${item.category}`.toLowerCase();
    return (!search || haystack.includes(search))
      && (type === "all" || item.type === type)
      && (status === "all" || item.status === status)
      && (category === "all" || item.category === category);
  });

  qs("#listings-grid").innerHTML = filtered.length
    ? filtered.map((item) => `
        <article class="listing-card">
          <div class="listing-head">
            <div>
              <span class="listing-type">${capitalize(item.type)}</span>
              <h3>${escapeHtml(item.itemName)}</h3>
            </div>
            ${badge(capitalize(item.status))}
          </div>
          <p>${escapeHtml(item.description)}</p>
          <div class="tag-row">
            ${badge(item.category)}
            ${badge(item.location)}
            ${badge(formatDate(item.listingDate))}
          </div>
          <div class="hero-actions">
            <button class="button primary" type="button" onclick="openDetail(${item.id})">Open detail</button>
            ${item.permissions?.canEdit ? `<button class="button ghost" type="button" onclick="prefillEdit(${item.id})">Edit</button>` : ""}
            ${state.user && state.user.role === "admin" ? `<button class="button danger" type="button" onclick="adminResolve(${item.id})">Mark resolved</button>` : ""}
          </div>
        </article>
      `).join("")
    : `<article class="panel"><h3>No listings match these filters.</h3><p>Try a different search or submit a new report.</p></article>`;
}

async function openDetail(id) {
  const data = await api(`/api/listings/${id}`);
  state.currentListing = data.listing;
  qs("#detail-section").classList.remove("hidden");
  qs('#claim-form input[name="listingId"]').value = id;
  qs("#detail-card").innerHTML = `
    <span class="listing-type">${capitalize(data.listing.type)}</span>
    <h3>${escapeHtml(data.listing.itemName)}</h3>
    <p>${escapeHtml(data.listing.description)}</p>
    <div class="tag-row">
      ${badge(data.listing.category)}
      ${badge(data.listing.location)}
      ${badge(data.listing.color || "No color set")}
      ${badge(`Contact: ${data.listing.contactPhone}`)}
      ${badge(capitalize(data.listing.status))}
    </div>
  `;
  qs("#detail-owner-actions").innerHTML = data.listing.permissions?.canEdit ? `
    <button class="button ghost" type="button" onclick="prefillEdit(${data.listing.id})">Edit listing</button>
    <button class="button danger" type="button" onclick="deleteListing(${data.listing.id})">Delete listing</button>
  ` : "";
  qs("#matches-list").innerHTML = data.matches.length
    ? data.matches.map((item) => stackItem(`${item.itemName} (${item.matchScore}% match)`, `${item.location} | ${item.category}`)).join("")
    : `<div class="stack-item"><span>No strong suggestions yet.</span><strong>0</strong></div>`;
  qs("#claims-list").innerHTML = data.listing.claims.length
    ? data.listing.claims.map((claim) => claimItem(claim, data.listing.permissions?.canModerate, data.listing.id)).join("")
    : `<div class="stack-item"><span>No claims submitted yet.</span><strong>0</strong></div>`;
  qs("#claim-form").classList.toggle("hidden", !data.listing.permissions?.canClaim);
  qs("#detail-section").scrollIntoView({ behavior: "smooth" });
}

async function submitLogin(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries()))
    });
    state.user = data.user;
    qs("#auth-feedback").textContent = "Signed in successfully.";
    qs("#auth-feedback").className = "feedback success";
    qs("#auth-dialog").close();
    applySessionUi();
    await loadListings();
  } catch (error) {
    showAuthError(error);
  }
}

async function submitRegister(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries()))
    });
    state.user = data.user;
    qs("#auth-feedback").textContent = "Account created and signed in.";
    qs("#auth-feedback").className = "feedback success";
    qs("#auth-dialog").close();
    applySessionUi();
    await loadListings();
  } catch (error) {
    showAuthError(error);
  }
}

async function submitReport(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const payload = Object.fromEntries(form.entries());
    const listingId = payload.listingId;
    delete payload.listingId;
    const data = await api(listingId ? `/api/listings/${listingId}/update` : "/api/listings", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    qs("#report-feedback").textContent = listingId ? "Listing updated successfully." : "Report submitted successfully.";
    qs("#report-feedback").className = "feedback success";
    resetReportForm();
    await loadListings();
    if (state.user) await loadMyData();
    await openDetail(data.listing.id);
  } catch (error) {
    qs("#report-feedback").textContent = error.message;
    qs("#report-feedback").className = "feedback error";
  }
}

async function submitClaim(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const listingId = form.get("listingId");
    await api(`/api/listings/${listingId}/claim`, {
      method: "POST",
      body: JSON.stringify({ proofText: form.get("proofText") })
    });
    qs("#claim-feedback").textContent = "Claim submitted successfully.";
    qs("#claim-feedback").className = "feedback success";
    await loadListings();
    if (state.user) await loadMyData();
    await openDetail(Number(listingId));
    event.currentTarget.reset();
    qs('#claim-form input[name="listingId"]').value = listingId;
  } catch (error) {
    qs("#claim-feedback").textContent = error.message;
    qs("#claim-feedback").className = "feedback error";
  }
}

async function adminResolve(id) {
  try {
    await api(`/api/listings/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status: "resolved" })
    });
    await loadListings();
    if (state.user) await loadMyData();
    await loadAnalytics();
    if (state.currentListing && state.currentListing.id === id) {
      await openDetail(id);
    }
  } catch (error) {
    alert(error.message);
  }
}

async function adminUpdateClaim(claimId, status, listingId) {
  try {
    await api(`/api/claims/${claimId}/status`, {
      method: "POST",
      body: JSON.stringify({ status })
    });
    await loadListings();
    if (state.user) await loadMyData();
    await loadAnalytics();
    await openDetail(listingId);
  } catch (error) {
    alert(error.message);
  }
}

async function loadAnalytics() {
  try {
    const data = await api("/api/analytics");
    qs("#admin-metrics").innerHTML = [
      metricCard(data.totalReports, "Total reports"),
      metricCard(data.pendingClaims, "Pending claims"),
      metricCard(`${data.recoveryRate}%`, "Recovery rate"),
      metricCard(data.resolvedReports, "Resolved cases")
    ].join("");
    qs("#admin-categories").innerHTML = data.byCategory.map((item) => stackItem(item.label, item.count)).join("");
    qs("#admin-locations").innerHTML = data.byLocation.map((item) => stackItem(item.label, item.count)).join("");
  } catch {}
}

async function logout() {
  await api("/api/logout", { method: "POST", body: "{}" });
  state.user = null;
  state.myListings = [];
  state.myClaims = [];
  resetReportForm();
  applySessionUi();
  await loadListings();
}

async function prefillEdit(id) {
  const data = await api(`/api/listings/${id}`);
  const form = qs("#report-form");
  form.listingId.value = data.listing.id;
  form.type.value = data.listing.type;
  form.itemName.value = data.listing.itemName;
  form.category.value = data.listing.category;
  form.location.value = data.listing.location;
  form.listingDate.value = data.listing.listingDate;
  form.color.value = data.listing.color || "";
  form.contactPhone.value = data.listing.permissions?.canSeeContact && !data.listing.contactPhone.startsWith("Hidden until")
    ? data.listing.contactPhone
    : "";
  form.photoUrl.value = data.listing.photoUrl || "";
  form.description.value = data.listing.description;
  qs("#cancel-edit").classList.remove("hidden");
  qs("#report").scrollIntoView({ behavior: "smooth" });
}

function resetReportForm() {
  const form = qs("#report-form");
  form.reset();
  form.listingId.value = "";
  form.listingDate.value = new Date().toISOString().slice(0, 10);
  qs("#cancel-edit").classList.add("hidden");
}

async function deleteListing(id) {
  if (!confirm("Delete this listing?")) return;
  try {
    await api(`/api/listings/${id}/delete`, { method: "POST", body: "{}" });
    qs("#detail-section").classList.add("hidden");
    await loadListings();
    if (state.user) await loadMyData();
  } catch (error) {
    alert(error.message);
  }
}

function summarize(listings) {
  return {
    total: listings.length,
    found: listings.filter((item) => item.type === "found").length,
    open: listings.filter((item) => item.status === "open").length,
    claimed: listings.filter((item) => item.status === "claimed").length,
    resolved: listings.filter((item) => item.status === "resolved").length,
    pendingClaims: listings.reduce((sum, item) => sum + (item.claimsCount || 0), 0),
  };
}

function metricCard(value, label) {
  return `<article class="metric-card"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></article>`;
}

function stackItem(label, value) {
  return `<div class="stack-item"><span>${escapeHtml(String(label))}</span><strong>${escapeHtml(String(value))}</strong></div>`;
}

function claimItem(claim, canModerate, listingId) {
  return `
    <div class="stack-item">
      <span>${escapeHtml(claim.claimantName)} • ${escapeHtml(claim.proofText)}</span>
      <strong class="inline-actions">
        ${escapeHtml(capitalize(claim.status))}
        ${canModerate && claim.status === "pending" ? `
          <button class="mini-link" type="button" onclick="adminUpdateClaim(${claim.id}, 'approved', ${listingId})">Approve</button>
          <button class="mini-link" type="button" onclick="adminUpdateClaim(${claim.id}, 'rejected', ${listingId})">Reject</button>
        ` : ""}
      </strong>
    </div>
  `;
}

function badge(text) {
  return `<span class="badge">${escapeHtml(String(text))}</span>`;
}

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function formatDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showAuthError(error) {
  qs("#auth-feedback").textContent = error.message;
  qs("#auth-feedback").className = "feedback error";
}

function registerPwa() {
  qs('input[name="listingDate"]').value = new Date().toISOString().slice(0, 10);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.deferredPrompt = event;
    qs("#install-app").classList.remove("hidden");
  });
}

async function installApp() {
  if (!state.deferredPrompt) return;
  state.deferredPrompt.prompt();
  await state.deferredPrompt.userChoice;
  state.deferredPrompt = null;
  qs("#install-app").classList.add("hidden");
}

window.openDetail = openDetail;
window.adminResolve = adminResolve;
window.adminUpdateClaim = adminUpdateClaim;
window.prefillEdit = prefillEdit;
window.deleteListing = deleteListing;
