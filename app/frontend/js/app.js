// =============================================================================
// StayFinder — app.js
// =============================================================================

const API_BASE = 'http://localhost:8000';

// =============================================================================
// UTILITIES
// =============================================================================

function el(id) { return document.getElementById(id); }

function showLoading(container) {
  container.innerHTML = `
    <div class="loading-spinner">
      <div class="spinner"></div>
      <span>Running...</span>
    </div>`;
}

function showError(container, message) {
  container.innerHTML = `<div class="error-message">⚠ ${message}</div>`;
}

function buildTable(rows) {
  if (!rows || rows.length === 0) {
    return '<p style="font-size:0.85rem;color:var(--ink-muted);padding:8px 0;">No rows returned.</p>';
  }

  const headers = Object.keys(rows[0]);

  const thead = `<thead><tr>${
    headers.map(h => `<th>${h.replace(/_/g, ' ')}</th>`).join('')
  }</tr></thead>`;

  const tbody = `<tbody>${
    rows.map(row =>
      `<tr>${headers.map(h => `<td>${row[h] ?? '—'}</td>`).join('')}</tr>`
    ).join('')
  }</tbody>`;

  return `
    <div class="result-table-wrap">
      <table class="result-table">${thead}${tbody}</table>
    </div>
    <p class="result-count">${rows.length} row${rows.length !== 1 ? 's' : ''}</p>`;
}

function starsDisplay(rating) {
  const full  = Math.floor(rating);
  const half  = rating % 1 >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

// =============================================================================
// SEARCH
// =============================================================================

const searchBtn   = el('search-btn');
const queryInput  = el('query-input');
const resultsArea = el('results-area');
const filterChips = el('filter-chips');

let activeFilter = 'all';

// Filter chip selection
filterChips.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  filterChips.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  activeFilter = chip.dataset.filter;
});

// Submit on Enter (Shift+Enter for newline)
queryInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    runSearch();
  }
});

searchBtn.addEventListener('click', runSearch);

async function runSearch() {
  const query = queryInput.value.trim();
  if (!query) {
    queryInput.focus();
    return;
  }

  searchBtn.disabled = true;
  showLoading(resultsArea);

  try {
    const res = await fetch(`${API_BASE}/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, category: activeFilter === 'all' ? null : activeFilter })
    });

    if (!res.ok) throw new Error(`Server returned ${res.status}`);

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    showError(resultsArea, `Could not reach the backend. Make sure main.py is running on port 8000. (${err.message})`);
  } finally {
    searchBtn.disabled = false;
  }
}

function renderResults(data) {
  // data shape expected from /recommend:
  // { answer: string, hotels: [ { hotel_id, name, city, category, star_rating,
  //   price_per_night, avg_review_rating, review_count, amenities } ] }

  if (!data.hotels || data.hotels.length === 0) {
    resultsArea.innerHTML = `
      <div class="results-placeholder">
        <div class="placeholder-icon">◈</div>
        <p>No hotels matched your query. Try different keywords or remove the category filter.</p>
      </div>`;
    return;
  }

  const answerBlock = data.answer ? `
    <div class="ai-answer">
      <div class="ai-answer-label">AI Summary</div>
      ${escapeHtml(data.answer)}
    </div>` : '';

  const cards = data.hotels.map(h => `
    <div class="hotel-card">
      <div class="hotel-info">
        <div class="hotel-name">${escapeHtml(h.name)}</div>
        <div class="hotel-meta">
          <span>${escapeHtml(h.city)}</span>
          <span>${escapeHtml(h.category)}</span>
          <span>${h.star_rating} star${h.star_rating !== 1 ? 's' : ''}</span>
          ${h.review_count ? `<span>${h.review_count} review${h.review_count !== 1 ? 's' : ''}</span>` : ''}
        </div>
        ${h.amenities ? `<div class="hotel-summary">${escapeHtml(h.amenities)}</div>` : ''}
      </div>
      <div class="hotel-price">
        <div class="price-amount">$${Number(h.price_per_night).toFixed(0)}</div>
        <span class="price-label">per night</span>
        ${h.avg_review_rating ? `
          <div class="hotel-rating">
            ★ ${Number(h.avg_review_rating).toFixed(1)}
          </div>` : ''}
      </div>
    </div>`).join('');

  resultsArea.innerHTML = answerBlock + cards;
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// =============================================================================
// ANALYTICS — query cards
// =============================================================================

// Maps data-query attribute to backend endpoint path
const QUERY_ENDPOINTS = {
  agg1:  '/query/agg1',
  agg2:  '/query/agg2',
  join1: '/query/join1',
  join2: '/query/join2',
  sub1:  '/query/sub1',
  sub2:  '/query/sub2',
  cte1:  '/query/cte1',
  cte2:  '/query/cte2',
  win1:  '/query/win1',
  win2:  '/query/win2',
};

document.querySelectorAll('.query-card').forEach(card => {
  const btn       = card.querySelector('.btn-run');
  const queryKey  = card.dataset.query;
  const resultDiv = card.querySelector('.query-result');

  btn.addEventListener('click', () => runQuery(queryKey, btn, resultDiv));
});

async function runQuery(queryKey, btn, resultDiv) {
  const endpoint = QUERY_ENDPOINTS[queryKey];
  if (!endpoint) return;

  btn.disabled = true;
  btn.textContent = 'Running...';
  showLoading(resultDiv);

  try {
    const res = await fetch(`${API_BASE}${endpoint}`);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);

    const data = await res.json();
    // Backend should return { rows: [...] }
    resultDiv.innerHTML = buildTable(data.rows ?? data);
  } catch (err) {
    showError(resultDiv, `Query failed. Is main.py running? (${err.message})`);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Run query';
  }
}

// =============================================================================
// INIT
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Smooth active nav highlight on scroll
  const sections = document.querySelectorAll('section[id]');
  const navLinks  = document.querySelectorAll('.nav-links a');

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(a => {
          a.style.color = a.getAttribute('href') === `#${entry.target.id}`
            ? 'var(--ink)'
            : '';
        });
      }
    });
  }, { threshold: 0.4 });

  sections.forEach(s => observer.observe(s));
});