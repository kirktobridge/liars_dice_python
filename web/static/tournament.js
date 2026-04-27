/* tournament.js — Chart.js dashboard for the tournament simulator */

'use strict';

const MEDAL_COLORS = ['#FFD700', '#C0C0C0', '#CD7F32'];
const ACCENT       = '#c9a84c';
const CHART_BG     = 'rgba(255,255,255,0.06)';
const GRID_COLOR   = 'rgba(255,255,255,0.07)';
const TICK_COLOR   = '#7a6e58';

// Shared Chart.js defaults for dark theme
function baseScales(xTitle = '', yTitle = '') {
  return {
    x: {
      grid: { color: GRID_COLOR },
      ticks: { color: TICK_COLOR, font: { size: 10 } },
      title: xTitle ? { display: true, text: xTitle, color: TICK_COLOR, font: { size: 10 } } : {},
    },
    y: {
      grid: { color: GRID_COLOR },
      ticks: { color: TICK_COLOR, font: { size: 10 } },
      title: yTitle ? { display: true, text: yTitle, color: TICK_COLOR, font: { size: 10 } } : {},
    },
  };
}

function baseLegend(display = false) {
  return { display, labels: { color: '#c0b090', font: { size: 11 } } };
}

// ── helpers ──────────────────────────────────────────────────────────────────

function playerColors(n) {
  return Array.from({ length: n }, (_, i) => MEDAL_COLORS[i] || '#5B8DB8');
}

function riskLabel(v) {
  if (v <= 33) return `${v} (Conservative)`;
  if (v <= 66) return `${v} (Moderate)`;
  return `${v} (Aggressive)`;
}

function attLabel(v) {
  if (v <= 33) return `${v} (Oblivious)`;
  if (v <= 66) return `${v} (Observant)`;
  return `${v} (Eagle-eyed)`;
}

function cunnLabel(v) {
  if (v <= 33) return `${v} (Blinkered)`;
  if (v <= 66) return `${v} (Tactical)`;
  return `${v} (Masterful)`;
}

function buildHistogram(values, numBins = 28) {
  if (!values.length) return { labels: [], counts: [] };
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return { labels: [min], counts: [values.length] };
  const binWidth = Math.max(1, Math.ceil((max - min) / numBins));
  const n = Math.ceil((max - min) / binWidth) + 1;
  const counts = new Array(n).fill(0);
  const labels = Array.from({ length: n }, (_, i) => min + i * binWidth);
  values.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / binWidth), n - 1);
    counts[idx]++;
  });
  return { labels, counts, binWidth };
}

function downsamplePairs(xs, ys, maxN = 4000) {
  if (xs.length <= maxN) return xs.map((x, i) => ({ x, y: ys[i] }));
  const step = Math.ceil(xs.length / maxN);
  const pts = [];
  for (let i = 0; i < xs.length; i += step) pts.push({ x: xs[i], y: ys[i] });
  return pts;
}

function addInsightBadge(refId, insights) {
  const ref = document.getElementById(refId);
  if (!ref) return;
  const panel = ref.closest('.chart-panel');
  if (!panel) return;
  panel.querySelector('.insight-badge')?.remove();
  const items = insights.filter(Boolean);
  if (!items.length) return;
  const div = document.createElement('div');
  div.className = 'insight-badge';
  div.innerHTML = items.map(t => `<span class="insight-item">${t}</span>`).join('');
  panel.appendChild(div);
}

function buildNarrative(name, i, s) {
  const risk = s.profile_risk[i];
  const peer = s.profile_peer[i];
  const att  = s.profile_att[i];
  const cun  = s.profile_cun?.[i] ?? 50;
  const winPct   = s.profile_win_pct_float?.[i] ?? parseFloat(s.profile_win_pct[i]);
  const expected = 100 / (s.num_players || s.profile_players.length);
  const diff     = winPct - expected;

  const bidStyle = risk <= 33 ? 'cautious bidder'
    : risk <= 66 ? 'measured bidder'
    : 'aggressive bidder';
  const socialStyle = peer <= 33 ? 'sticks to their own read'
    : peer <= 66 ? 'susceptible to the crowd'
    : 'easily swayed by others';
  const attStyle = att <= 33 ? 'oblivious to opponents\' dice'
    : att <= 66 ? 'keeps a reasonable eye on the table'
    : 'hawk-eyed at the table';
  const cunStyle = cun <= 33 ? 'ignores seat position'
    : cun <= 66 ? 'reads the table order'
    : 'exploits seat position masterfully';

  const parts = [bidStyle, socialStyle, attStyle, cunStyle];

  const si = s.sorted_players.indexOf(name);
  if (si >= 0) {
    const cp   = s.chall_win_pct[si];
    const avgC = s.chall_win_pct.reduce((a, b) => a + b, 0) / s.chall_win_pct.length;
    parts.push(cp - avgC > 5  ? `sharp challenger (${cp}%)`
      : cp - avgC < -5         ? `poor challenger (${cp}%)`
      : `average challenger (${cp}%)`);

    const sa = s.spot_attempts[si];
    if (sa > 0) {
      const sp = s.spot_win_pct[si];
      parts.push(sp >= 50 ? `spot-ons pay off (${sp}%)` : `spot-ons rarely land (${sp}%)`);
    }
  }

  const winDesc = Math.abs(diff) < 1  ? 'right at expectation'
    : diff >= 10  ? `dominates &mdash; ${diff.toFixed(0)}pp above expected`
    : diff >= 3   ? `outperforms by ${diff.toFixed(0)}pp`
    : diff <= -10 ? `struggles &mdash; ${Math.abs(diff).toFixed(0)}pp below expected`
    : diff <= -3  ? `underperforms by ${Math.abs(diff).toFixed(0)}pp`
    : diff > 0    ? 'marginally ahead of expected'
    : 'marginally behind expected';
  parts.push(winDesc);

  return parts.join(' &middot; ');
}

function heatColor(v) {
  if (v === null || v === undefined) return '#111';
  const hue = Math.round(v * 120); // 0=red, 120=green
  return `hsl(${hue}, 65%, 35%)`;
}

// ── state & chart registry ───────────────────────────────────────────────────

let jobId       = null;
let pollTimer   = null;
const charts    = {};

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

// ── section visibility ───────────────────────────────────────────────────────

function showSection(name) {
  ['progress-section', 'error-section', 'results-section'].forEach(id => {
    document.getElementById(id).classList.add('hidden');
  });
  if (name) document.getElementById(name).classList.remove('hidden');
}

function showError(msg) {
  stopPolling();
  document.getElementById('error-msg').textContent = msg;
  showSection('error-section');
}

// ── form submission ───────────────────────────────────────────────────────────

document.getElementById('run-form').addEventListener('submit', async e => {
  e.preventDefault();
  const n          = parseInt(document.getElementById('n-games').value, 10);
  const numPlayers = parseInt(document.getElementById('num-players').value, 10);
  const errEl      = document.getElementById('form-error');

  if (!n || n < 1 || n > 10000) {
    errEl.textContent = 'Number of games must be between 1 and 10,000.';
    errEl.classList.remove('hidden');
    return;
  }
  errEl.classList.add('hidden');

  // Reset state
  stopPolling();
  document.getElementById('progress-msg').textContent =
    `SIMULATING ${n.toLocaleString()} GAMES WITH ${numPlayers} PLAYERS…`;
  document.getElementById('progress-sub').textContent = 'Hold your dice…';
  const fill = document.getElementById('progress-fill');
  fill.classList.remove('indeterminate');
  fill.style.width = '0%';
  showSection('progress-section');

  try {
    const resp = await fetch('/tournament/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ n, num_players: numPlayers }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || 'Failed to start simulation.');
      return;
    }
    const data = await resp.json();
    jobId = data.job_id;
    pollTimer = setInterval(pollStatus, 200);
  } catch (err) {
    showError(`Network error: ${err.message}`);
  }
});

// ── polling ───────────────────────────────────────────────────────────────────

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollStatus() {
  if (!jobId) return;
  try {
    const resp = await fetch(`/tournament/status/${jobId}`);
    if (!resp.ok) return;
    const data = await resp.json();

    const fill = document.getElementById('progress-fill');
    const pct  = Math.round((data.progress || 0) * 100);
    fill.style.width = `${pct}%`;
    document.getElementById('progress-sub').textContent = `${pct}% complete`;

    if (data.status === 'complete') {
      stopPolling();
      fill.style.width = '100%';
      document.getElementById('progress-sub').textContent = 'Complete! Rendering the spoils…';
      setTimeout(fetchAndRender, 200);
    } else if (data.status === 'error') {
      showError('The simulation encountered an error. Check server logs.');
    }
  } catch (_) { /* network hiccup — keep polling */ }
}

// ── fetch results ─────────────────────────────────────────────────────────────

async function fetchAndRender() {
  try {
    const resp = await fetch(`/tournament/results/${jobId}`);
    if (!resp.ok) {
      showError('Failed to fetch results from the server.');
      return;
    }
    const stats = await resp.json();
    renderDashboard(stats);
    showSection('results-section');
  } catch (err) {
    showError(`Failed to render dashboard: ${err.message}`);
  }
}

// ── dashboard ─────────────────────────────────────────────────────────────────

function renderDashboard(s) {
  renderSummary(s);
  renderWinRate(s);
  renderGameLength(s);
  renderSpotOn(s);
  renderChallengeAcc(s);
  renderBidScatter(s);
  renderBidRatio(s);
  renderProfiles(s);
  renderCorrelationCharts(s);
  renderEscalation(s);
  renderHeatmap(s);
  renderInsightBadges(s);
}

// ── 0. Summary chips ─────────────────────────────────────────────────────────

function renderSummary(s) {
  const el = document.getElementById('summary-stats');
  const chips = [
    { value: s.n_games.toLocaleString(), label: 'Games Simulated' },
    { value: s.num_players, label: 'Players per Game' },
    { value: s.mean_rounds.toFixed(1), label: 'Avg Rounds / Game' },
    { value: s.avg_bids_per_round.toFixed(1), label: 'Avg Bids / Round' },
    { value: s.fastest_rounds, label: `Fastest Game (seed ${s.fastest_seed})` },
    { value: s.longest_rounds, label: `Longest Game (seed ${s.longest_seed})` },
  ];
  el.innerHTML = chips.map(c => `
    <div class="stat-chip">
      <span class="stat-value">${c.value}</span>
      <span class="stat-label">${c.label}</span>
    </div>
  `).join('');
}

// ── 1. Win Rate (horizontal bar) ─────────────────────────────────────────────

function renderWinRate(s) {
  destroyChart('winRate');
  const ctx = document.getElementById('chart-win-rate').getContext('2d');
  charts.winRate = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: s.sorted_players,
      datasets: [{
        data: s.win_counts,
        backgroundColor: playerColors(s.sorted_players.length),
        borderWidth: 0,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: baseLegend(),
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const i = ctx.dataIndex;
              return ` ${ctx.parsed.x} wins (${s.win_pct[i]}%)`;
            },
          },
        },
      },
      scales: {
        ...baseScales('Wins'),
        y: { grid: { color: GRID_COLOR }, ticks: { color: '#c0b090', font: { size: 10 } } },
      },
    },
  });
}

// ── 2. Game Length Distribution (histogram) ──────────────────────────────────

function renderGameLength(s) {
  destroyChart('gameLength');
  const { labels, counts } = buildHistogram(s.rounds_series, 28);
  const ctx = document.getElementById('chart-game-length').getContext('2d');
  charts.gameLength = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: counts,
        backgroundColor: '#5B8DB8',
        borderWidth: 0,
        barPercentage: 1.0,
        categoryPercentage: 1.0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: baseLegend(),
        annotation: {
          annotations: {
            meanLine: {
              type: 'line',
              xMin: s.mean_rounds,
              xMax: s.mean_rounds,
              borderColor: '#FFD700',
              borderWidth: 2,
              borderDash: [5, 3],
              label: {
                display: true,
                content: `mean ${s.mean_rounds.toFixed(1)}`,
                color: '#FFD700',
                backgroundColor: 'rgba(0,0,0,0.6)',
                font: { size: 10 },
                position: 'start',
              },
            },
          },
        },
      },
      scales: baseScales('Rounds', 'Count'),
    },
  });
}

// ── 3. Spot On Accuracy (horizontal bar) ─────────────────────────────────────

function renderSpotOn(s) {
  destroyChart('spotOn');
  const ctx = document.getElementById('chart-spot-on').getContext('2d');
  charts.spotOn = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: s.sorted_players,
      datasets: [{
        data: s.spot_win_pct,
        backgroundColor: playerColors(s.sorted_players.length),
        borderWidth: 0,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: baseLegend(),
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const i = ctx.dataIndex;
              return ` ${ctx.parsed.x}%  (${s.spot_wins[i]}/${s.spot_attempts[i]} spot-ons)`;
            },
          },
        },
      },
      scales: {
        ...baseScales('Win %'),
        y: { grid: { color: GRID_COLOR }, ticks: { color: '#c0b090', font: { size: 10 } } },
      },
    },
  });
}

// ── 4. Challenge Accuracy (horizontal bar) ───────────────────────────────────

function renderChallengeAcc(s) {
  destroyChart('challengeAcc');
  const ctx = document.getElementById('chart-challenge-acc').getContext('2d');
  charts.challengeAcc = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: s.sorted_players,
      datasets: [{
        data: s.chall_win_pct,
        backgroundColor: playerColors(s.sorted_players.length),
        borderWidth: 0,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: baseLegend(),
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const i = ctx.dataIndex;
              return ` ${ctx.parsed.x}%  (${s.chall_won[i]}/${s.chall_called[i]} challenges)`;
            },
          },
        },
      },
      scales: {
        ...baseScales('Win %'),
        y: { grid: { color: GRID_COLOR }, ticks: { color: '#c0b090', font: { size: 10 } } },
      },
    },
  });
}

// ── 5. Bid vs. Actual Count at Challenge (scatter) ───────────────────────────

function renderBidScatter(s) {
  destroyChart('bidScatter');
  const maxV = s.scatter_max_val || 1;
  const ctx  = document.getElementById('chart-bid-scatter').getContext('2d');
  charts.bidScatter = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: 'Correct call',
          data: downsamplePairs(s.scatter_success_claimed, s.scatter_success_actual),
          backgroundColor: 'rgba(0,204,0,0.35)',
          pointRadius: 2,
          pointHoverRadius: 4,
          order: 2,
        },
        {
          label: 'Failed call',
          data: downsamplePairs(s.scatter_fail_claimed, s.scatter_fail_actual),
          backgroundColor: 'rgba(255,68,68,0.35)',
          pointRadius: 2,
          pointHoverRadius: 4,
          order: 2,
        },
        {
          label: 'y = x',
          type: 'line',
          data: [{ x: 0, y: 0 }, { x: maxV, y: maxV }],
          borderColor: 'rgba(255,255,255,0.25)',
          borderDash: [5, 3],
          pointRadius: 0,
          fill: false,
          tension: 0,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: baseLegend(true) },
      scales: baseScales('Bid Count Claimed', 'Actual Count'),
    },
  });
}

// ── 6. Challenge Accuracy by Bid Ratio (stacked bar) ─────────────────────────

function renderBidRatio(s) {
  destroyChart('bidRatio');
  const ctx = document.getElementById('chart-bid-ratio').getContext('2d');
  charts.bidRatio = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: s.bucket_labels,
      datasets: [
        {
          label: 'Correct call',
          data: s.bucket_success,
          backgroundColor: '#00CC00',
          stack: 'stack',
        },
        {
          label: 'Wrong call',
          data: s.bucket_fail,
          backgroundColor: '#FF4444',
          stack: 'stack',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: baseLegend(true) },
      scales: {
        ...baseScales('Bid / Bidder Dice', 'Rate'),
        y: {
          stacked: true,
          max: 1.0,
          grid: { color: GRID_COLOR },
          ticks: {
            color: TICK_COLOR,
            font: { size: 10 },
            callback: v => `${(v * 100).toFixed(0)}%`,
          },
        },
        x: { stacked: true, grid: { color: GRID_COLOR }, ticks: { color: TICK_COLOR, font: { size: 10 } } },
      },
    },
  });
}

// ── 7. Player Profiles (HTML table with narrative rows) ──────────────────────

function renderProfiles(s) {
  const headers = ['Player', 'Wins', 'Win %', 'Risk Appetite', 'Peer Pressure', 'Attentiveness', 'Positional Cunning'];
  let html = `<table class="profiles-table"><thead><tr>${
    headers.map(h => `<th>${h}</th>`).join('')
  }</tr></thead><tbody>`;

  s.profile_players.forEach((name, i) => {
    const alt = i % 2 === 1 ? ' row-alt' : '';
    html += `<tr class="${alt}">
      <td>${name}</td>
      <td>${s.profile_wins[i]}</td>
      <td>${s.profile_win_pct[i]}</td>
      <td>${riskLabel(s.profile_risk[i])}</td>
      <td>${s.profile_peer[i]}</td>
      <td>${attLabel(s.profile_att[i])}</td>
      <td>${cunnLabel(s.profile_cun?.[i] ?? 50)}</td>
    </tr>
    <tr class="narrative-row${alt}">
      <td colspan="7">${buildNarrative(name, i, s)}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  document.getElementById('table-profiles').innerHTML = html;
}

// ── 8. Bid Escalation Curve (line chart) ─────────────────────────────────────

function renderEscalation(s) {
  destroyChart('escalation');
  const ctx = document.getElementById('chart-escalation').getContext('2d');
  charts.escalation = new Chart(ctx, {
    type: 'line',
    data: {
      labels: s.escalation_bid_count,
      datasets: [{
        data: s.escalation_avg_claimed,
        borderColor: ACCENT,
        backgroundColor: 'rgba(201,168,76,0.08)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: ACCENT,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: baseLegend() },
      scales: baseScales('Bids in Round', 'Avg Claimed Count'),
    },
  });
}

// ── 11. Insight badges ────────────────────────────────────────────────────────

function renderInsightBadges(s) {
  // Win Rate
  const expected = 100 / s.num_players;
  const leadDiff = (parseFloat(s.win_pct[0]) - expected).toFixed(1);
  const lastIdx  = s.sorted_players.length - 1;
  const lastDiff = (parseFloat(s.win_pct[lastIdx]) - expected).toFixed(1);
  addInsightBadge('chart-win-rate', [
    `Expected: ${expected.toFixed(1)}% each`,
    `${s.sorted_players[0]}: ${leadDiff >= 0 ? '+' : ''}${leadDiff}pp vs expected`,
    lastIdx > 0 ? `${s.sorted_players[lastIdx]}: ${lastDiff}pp vs expected` : null,
  ]);

  // Game Length
  if (s.rounds_series?.length) {
    const sorted   = [...s.rounds_series].sort((a, b) => a - b);
    const median   = sorted[Math.floor(sorted.length / 2)];
    const belowPct = Math.round(sorted.filter(v => v <= s.mean_rounds).length / sorted.length * 100);
    addInsightBadge('chart-game-length', [
      `Median: ${median} rounds`,
      `${belowPct}% of games end at or below the mean`,
    ]);
  }

  // Spot On
  const maxSpotPct = Math.max(...s.spot_win_pct);
  const maxSpotIdx = s.spot_win_pct.indexOf(maxSpotPct);
  const totalSpot  = s.spot_attempts.reduce((a, b) => a + b, 0);
  addInsightBadge('chart-spot-on', [
    `Best: ${s.sorted_players[maxSpotIdx]} at ${maxSpotPct}%`,
    `${totalSpot.toLocaleString()} spot-ons attempted total`,
  ]);

  // Challenge Accuracy
  const maxChallPct = Math.max(...s.chall_win_pct);
  const maxChallIdx = s.chall_win_pct.indexOf(maxChallPct);
  const avgChall    = (s.chall_win_pct.reduce((a, b) => a + b, 0) / s.chall_win_pct.length).toFixed(1);
  const totalChall  = s.chall_called.reduce((a, b) => a + b, 0);
  addInsightBadge('chart-challenge-acc', [
    `Best: ${s.sorted_players[maxChallIdx]} at ${maxChallPct}%`,
    `Tournament avg: ${avgChall}%`,
    `${totalChall.toLocaleString()} challenges called`,
  ]);

  // Bid Scatter — avg overstatement at moment of challenge
  const allClaimed = [...s.scatter_success_claimed, ...s.scatter_fail_claimed];
  const allActual  = [...s.scatter_success_actual,  ...s.scatter_fail_actual];
  if (allClaimed.length) {
    const avgOver = (allClaimed.reduce((acc, v, i) => acc + v - allActual[i], 0) / allClaimed.length).toFixed(1);
    addInsightBadge('chart-bid-scatter', [
      `${totalChall.toLocaleString()} total challenges`,
      `At challenge, bid exceeds actual by ~${avgOver} dice on average`,
    ]);
  }

  // Bid Ratio
  let bestChalIdx = -1, bestChalVal = -Infinity;
  let bestBluffIdx = -1, bestBluffVal = -Infinity;
  s.bucket_success.forEach((v, i) => { if (v !== null && v > bestChalVal)  { bestChalVal  = v; bestChalIdx  = i; } });
  s.bucket_fail.forEach(   (v, i) => { if (v !== null && v > bestBluffVal) { bestBluffVal = v; bestBluffIdx = i; } });
  addInsightBadge('chart-bid-ratio', [
    bestChalIdx  >= 0 ? `Best to challenge: ${s.bucket_labels[bestChalIdx]} ratio (${Math.round(bestChalVal * 100)}% accuracy)` : null,
    bestBluffIdx >= 0 ? `Safest bluff: ${s.bucket_labels[bestBluffIdx]} ratio (challengers win only ${Math.round(s.bucket_success[bestBluffIdx] * 100)}%)` : null,
  ]);

  // Escalation
  if (s.escalation_avg_claimed?.length) {
    const peak    = Math.max(...s.escalation_avg_claimed);
    const peakBid = s.escalation_bid_count[s.escalation_avg_claimed.indexOf(peak)];
    const first   = s.escalation_avg_claimed[0];
    addInsightBadge('chart-escalation', [
      `Opens at ~${first.toFixed(1)} claimed &middot; peaks at ~${peak.toFixed(1)} by bid #${peakBid}`,
    ]);
  }
}

// ── custom tournament ─────────────────────────────────────────────────────────

let ALL_NAMES = [];

async function loadPlayerNames() {
  try {
    const resp = await fetch('/tournament/player-names');
    if (resp.ok) ALL_NAMES = (await resp.json()).names;
  } catch (_) {}
}

function getUsedNames() {
  return Array.from(document.querySelectorAll('.custom-name-select')).map(s => s.value);
}

function refreshCustomControls() {
  const rows = document.querySelectorAll('.custom-player-row');
  document.getElementById('btn-add-player').disabled = rows.length >= 8;
  const used = new Set(getUsedNames());
  document.querySelectorAll('.custom-name-select').forEach(sel => {
    const current = sel.value;
    Array.from(sel.options).forEach(opt => {
      opt.disabled = used.has(opt.value) && opt.value !== current;
    });
  });
  document.querySelectorAll('.btn-remove-player').forEach(btn => {
    btn.disabled = rows.length <= 2;
  });
}

function traitDisplayLabel(type, v) {
  if (type === 'risk') return riskLabel(v);
  if (type === 'att')  return attLabel(v);
  if (type === 'cun')  return cunnLabel(v);
  return String(v);
}

function addPlayerRow(name, risk = 50, peer = 50, att = 50, cun = 50) {
  const list = document.getElementById('custom-player-list');
  const row  = document.createElement('div');
  row.className = 'custom-player-row';

  const nameOpts = ALL_NAMES.map(n =>
    `<option value="${n}"${n === name ? ' selected' : ''}>${n}</option>`
  ).join('');

  row.innerHTML = `
    <select class="custom-name-select">${nameOpts}</select>
    <div class="custom-row-traits">
      <div class="trait-group">
        <label>Risk Appetite</label>
        <input type="range" class="trait-slider" min="1" max="100" value="${risk}" data-trait="risk">
        <span class="trait-value">${traitDisplayLabel('risk', risk)}</span>
      </div>
      <div class="trait-group">
        <label>Peer Pressure</label>
        <input type="range" class="trait-slider" min="1" max="100" value="${peer}" data-trait="peer">
        <span class="trait-value">${peer}</span>
      </div>
      <div class="trait-group">
        <label>Attentiveness</label>
        <input type="range" class="trait-slider" min="1" max="100" value="${att}" data-trait="att">
        <span class="trait-value">${traitDisplayLabel('att', att)}</span>
      </div>
      <div class="trait-group">
        <label>Positional Cunning</label>
        <input type="range" class="trait-slider" min="1" max="100" value="${cun}" data-trait="cun">
        <span class="trait-value">${traitDisplayLabel('cun', cun)}</span>
      </div>
    </div>
    <button class="btn-remove-player" type="button" title="Remove player">✕</button>
  `;

  row.querySelectorAll('.trait-slider').forEach(slider => {
    slider.addEventListener('input', () => {
      const v = parseInt(slider.value, 10);
      slider.nextElementSibling.textContent = traitDisplayLabel(slider.dataset.trait, v);
    });
  });

  row.querySelector('.custom-name-select').addEventListener('change', refreshCustomControls);

  row.querySelector('.btn-remove-player').addEventListener('click', () => {
    row.remove();
    refreshCustomControls();
  });

  list.appendChild(row);
  refreshCustomControls();
}

function initCustomScreen() {
  document.getElementById('custom-player-list').innerHTML = '';
  ALL_NAMES.slice(0, 4).forEach(name => addPlayerRow(name));
}

// Mode toggle
document.getElementById('btn-mode-standard').addEventListener('click', () => {
  document.getElementById('setup-section').classList.remove('hidden');
  document.getElementById('custom-section').classList.add('hidden');
  document.getElementById('btn-mode-standard').classList.add('active');
  document.getElementById('btn-mode-custom').classList.remove('active');
});

document.getElementById('btn-mode-custom').addEventListener('click', () => {
  document.getElementById('setup-section').classList.add('hidden');
  document.getElementById('custom-section').classList.remove('hidden');
  document.getElementById('btn-mode-standard').classList.remove('active');
  document.getElementById('btn-mode-custom').classList.add('active');
  if (document.querySelectorAll('.custom-player-row').length === 0) initCustomScreen();
});

// Add pirate button
document.getElementById('btn-add-player').addEventListener('click', () => {
  const used = new Set(getUsedNames());
  const next = ALL_NAMES.find(n => !used.has(n)) || ALL_NAMES[0];
  addPlayerRow(next);
});

// Custom run form
document.getElementById('custom-run-form').addEventListener('submit', async e => {
  e.preventDefault();
  const n     = parseInt(document.getElementById('custom-n-games').value, 10);
  const errEl = document.getElementById('custom-form-error');

  if (!n || n < 1 || n > 10000) {
    errEl.textContent = 'Number of games must be between 1 and 10,000.';
    errEl.classList.remove('hidden');
    return;
  }
  errEl.classList.add('hidden');

  const rows = document.querySelectorAll('.custom-player-row');
  const players = Array.from(rows).map(row => ({
    name:                row.querySelector('.custom-name-select').value,
    risk_appetite:       parseInt(row.querySelector('[data-trait="risk"]').value, 10),
    peer_pressure_score: parseInt(row.querySelector('[data-trait="peer"]').value, 10),
    attentiveness_score: parseInt(row.querySelector('[data-trait="att"]').value, 10),
    positional_cunning:  parseInt(row.querySelector('[data-trait="cun"]').value, 10),
  }));

  stopPolling();
  document.getElementById('progress-msg').textContent =
    `SIMULATING ${n.toLocaleString()} CUSTOM GAMES WITH ${players.length} PLAYERS…`;
  document.getElementById('progress-sub').textContent = 'Hold your dice…';
  const fill = document.getElementById('progress-fill');
  fill.classList.remove('indeterminate');
  fill.style.width = '0%';
  showSection('progress-section');

  try {
    const resp = await fetch('/tournament/run-custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ n, players }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || 'Failed to start simulation.');
      return;
    }
    const data = await resp.json();
    jobId = data.job_id;
    pollTimer = setInterval(pollStatus, 200);
  } catch (err) {
    showError(`Network error: ${err.message}`);
  }
});

// Load names on page load
loadPlayerNames();

// ── 9. Trait vs Win Rate (scatter charts) ────────────────────────────────────

function linearRegression(xs, ys) {
  const n = xs.length;
  if (n < 2) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
  const den = xs.reduce((s, x) => s + (x - mx) ** 2, 0);
  if (den === 0) return null;
  const slope = num / den;
  const intercept = my - slope * mx;
  const ssTot = ys.reduce((s, y) => s + (y - my) ** 2, 0);
  const ssRes = ys.reduce((s, y, i) => s + (y - (slope * xs[i] + intercept)) ** 2, 0);
  const r2 = ssTot === 0 ? 0 : 1 - ssRes / ssTot;
  return { slope, intercept, r2 };
}

function makeTraitChart(canvasId, traitValues, winPcts, playerNames, xLabel, color) {
  destroyChart(canvasId);
  const reg = linearRegression(traitValues, winPcts);
  const lineData = reg
    ? [{ x: 0, y: reg.intercept }, { x: 105, y: reg.slope * 105 + reg.intercept }]
    : [];

  const ctx = document.getElementById(canvasId).getContext('2d');
  charts[canvasId] = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          data: traitValues.map((v, i) => ({ x: v, y: winPcts[i] })),
          backgroundColor: color,
          pointRadius: 7,
          pointHoverRadius: 9,
          order: 2,
        },
        ...(reg ? [{
          type: 'line',
          label: `R² = ${reg.r2.toFixed(2)}`,
          data: lineData,
          borderColor: 'rgba(255,255,255,0.35)',
          borderWidth: 1.5,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          tension: 0,
          order: 1,
        }] : []),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: !!reg, labels: { color: '#8a7e68', font: { size: 10 }, boxWidth: 20 } },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.pointRadius === 0
              ? null
              : `${playerNames[ctx.dataIndex]}: ${ctx.parsed.y}%`,
          },
          filter: item => item.dataset.pointRadius !== 0,
        },
      },
      scales: {
        x: {
          min: 0, max: 105,
          grid: { color: GRID_COLOR },
          ticks: { color: TICK_COLOR, font: { size: 10 } },
          title: { display: true, text: xLabel, color: TICK_COLOR, font: { size: 10 } },
        },
        y: {
          min: 0, max: 100,
          grid: { color: GRID_COLOR },
          ticks: { color: TICK_COLOR, font: { size: 10 }, callback: v => `${v}%` },
          title: { display: true, text: 'Win %', color: TICK_COLOR, font: { size: 10 } },
        },
      },
    },
  });
}

function renderCorrelationCharts(s) {
  const section = document.getElementById('correlation-section');
  if (!s.profile_players || s.profile_players.length < 2) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  const names   = s.profile_players;
  const winPcts = s.profile_win_pct_float;
  makeTraitChart('corrRiskChart', s.profile_risk,              winPcts, names, 'Risk Appetite (1–100)',      '#c9a84c');
  makeTraitChart('corrPeerChart', s.profile_peer,              winPcts, names, 'Peer Pressure (1–100)',      '#5B8DB8');
  makeTraitChart('corrAttChart',  s.profile_att,               winPcts, names, 'Attentiveness (1–100)',      '#7ecf86');
  makeTraitChart('corrCunChart',  s.profile_cun ?? [],         winPcts, names, 'Positional Cunning (1–100)', '#b07ecf');
}

// ── 10. Challenge Success Heatmap (HTML table) ────────────────────────────────

function renderHeatmap(s) {
  const { heat_x, heat_y, heat_z, heat_text, heat_n } = s;
  let html = '<table class="heatmap-table"><thead><tr><th>Dice ↓ / Bid →</th>';
  heat_x.forEach(x => { html += `<th>${x}</th>`; });
  html += '</tr></thead><tbody>';

  heat_y.forEach((y, row) => {
    html += `<tr><th>${y}d</th>`;
    heat_x.forEach((_, col) => {
      const v    = heat_z[row]?.[col];
      const text = heat_text[row]?.[col] || '';
      const n    = heat_n[row]?.[col] ?? 0;
      const bg   = heatColor(v);
      const title = v !== null && v !== undefined
        ? `Bid: ${heat_x[col]}, Dice: ${y}, Success: ${text}, n=${n}`
        : `No data`;
      html += `<td style="background:${bg}" title="${title}">${text}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  document.getElementById('table-heatmap').innerHTML = html;
}
