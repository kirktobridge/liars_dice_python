'use strict';

// ============================================================
// CONSTANTS
// ============================================================
const MAX_PLAYERS = 8;
const MAX_FEED_ITEMS = 10;

// Pip coordinates (cx%, cy%) within a 100×100 viewBox
const PIP_POSITIONS = {
  1: [[50, 50]],
  2: [[30, 30], [70, 70]],
  3: [[30, 30], [50, 50], [70, 70]],
  4: [[30, 30], [70, 30], [30, 70], [70, 70]],
  5: [[30, 30], [70, 30], [50, 50], [30, 70], [70, 70]],
  6: [[30, 25], [70, 25], [30, 50], [70, 50], [30, 75], [70, 75]],
};

const DICE_UNICODE = { 1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅' };

// ============================================================
// STATE
// ============================================================
let ws              = null;
let humanName       = '';
let storedNumPlayers = 3;
let humanDice       = [];
let isHumanTurn     = false;
let currentRequest  = null;   // OpeningBidRequest | DecisionRequest
let selectedFace    = 1;
let eventLog        = [];
let lastSnapshot    = null;
let currentTurnPlayer = null; // tracks who's about to act, from turn_started

// ============================================================
// DOM SHORTHAND
// ============================================================
const $ = id => document.getElementById(id);

// ============================================================
// DIE FACE SVG
// ============================================================
function makeDieSVG(face, size) {
  const pips = PIP_POSITIONS[face] || PIP_POSITIONS[1];
  const ns = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.classList.add('die-face');

  // Die body
  const rect = document.createElementNS(ns, 'rect');
  rect.setAttribute('x', '4'); rect.setAttribute('y', '4');
  rect.setAttribute('width', '92'); rect.setAttribute('height', '92');
  rect.setAttribute('rx', '16'); rect.setAttribute('ry', '16');
  rect.setAttribute('fill', '#f4e5c2');
  rect.setAttribute('stroke', '#c8a84a');
  rect.setAttribute('stroke-width', '3');
  svg.appendChild(rect);

  // Inner bevel (subtle)
  const inner = document.createElementNS(ns, 'rect');
  inner.setAttribute('x', '8'); inner.setAttribute('y', '8');
  inner.setAttribute('width', '84'); inner.setAttribute('height', '84');
  inner.setAttribute('rx', '13'); inner.setAttribute('ry', '13');
  inner.setAttribute('fill', 'none');
  inner.setAttribute('stroke', 'rgba(255,255,255,0.25)');
  inner.setAttribute('stroke-width', '1.5');
  svg.appendChild(inner);

  // Pips
  for (const [cx, cy] of pips) {
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', cx);
    circle.setAttribute('cy', cy);
    circle.setAttribute('r', '9');
    circle.setAttribute('fill', '#1c1208');
    svg.appendChild(circle);
  }

  return svg;
}

// ============================================================
// ROSTER RENDERING
// ============================================================
function renderRoster(snap) {
  const roster = $('player-roster');
  if (!roster) return;

  roster.innerHTML = '';

  const activeTurn = isHumanTurn
    ? humanName
    : (currentTurnPlayer || snap.current_player);

  for (const p of snap.active_players) {
    const isHuman     = p.player_type === 'HUMAN';
    const isCurrent   = p.name === activeTurn;
    const isElim      = p.is_eliminated;

    const row = document.createElement('div');
    row.className = [
      'player-row',
      isHuman   ? 'player-row-human'  : '',
      isCurrent ? 'player-row-active' : '',
    ].filter(Boolean).join(' ');
    row.dataset.playerName = p.name;

    // Turn dot
    const dot = document.createElement('div');
    dot.style.cssText = `
      width:8px; height:8px; border-radius:50%; flex-shrink:0;
      background:${isCurrent ? '#c9a84c' : '#3a3028'};
    `;
    if (isCurrent) dot.classList.add('pulse-dot');
    row.appendChild(dot);

    // Name
    const nameEl = document.createElement('span');
    nameEl.style.cssText = 'flex:1; font-size:0.78rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    if (isElim) {
      nameEl.style.textDecoration = 'line-through';
      nameEl.style.color = '#4a4040';
    } else if (isHuman) {
      nameEl.style.color = '#d4b96a';
      nameEl.style.fontFamily = "'Cinzel', serif";
      nameEl.style.fontWeight = '600';
    } else {
      nameEl.style.color = '#b8a898';
    }
    nameEl.textContent = p.name;
    row.appendChild(nameEl);

    // Dice pips
    const diceEl = document.createElement('div');
    diceEl.style.cssText = 'display:flex; gap:3px; align-items:center; flex-shrink:0;';
    if (isElim) {
      const x = document.createElement('span');
      x.style.cssText = 'color:#4a3a3a; font-size:0.7rem;';
      x.textContent = '✗';
      diceEl.appendChild(x);
    } else {
      for (let i = 0; i < p.num_dice; i++) {
        const pip = document.createElement('div');
        pip.style.cssText = `
          width:5px; height:5px; border-radius:1px;
          background:${isHuman ? '#c9a84c' : '#6a5a48'};
          opacity:0.85;
        `;
        diceEl.appendChild(pip);
      }
    }
    row.appendChild(diceEl);
    roster.appendChild(row);
  }
}

// ============================================================
// BID DISPLAY
// ============================================================
function renderBid(snap) {
  const bidDisplay = $('bid-display');
  if (!bidDisplay) return;

  if (!snap.prev_bid) {
    bidDisplay.innerHTML =
      '<div style="color:#4a4040; font-style:italic; font-family:\'Crimson Text\',serif; font-size:0.95rem;">' +
      'No bid yet — open the round' +
      '</div>';
    return;
  }

  const { count, face } = snap.prev_bid;
  const bidder = snap.prev_bidder || '?';

  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';
  wrapper.classList.add('bid-pulse');

  const countEl = document.createElement('div');
  countEl.style.cssText = `
    font-family:'Cinzel',serif; font-size:2.4rem; font-weight:700;
    color:#c9a84c; line-height:1; text-shadow:0 0 12px rgba(201,168,76,0.3);
  `;
  countEl.textContent = count + '×';
  wrapper.appendChild(countEl);

  const dieWrapper = document.createElement('div');
  dieWrapper.classList.add('die-wrapper');
  dieWrapper.appendChild(makeDieSVG(face, 68));
  wrapper.appendChild(dieWrapper);

  const bidderEl = document.createElement('div');
  bidderEl.style.cssText = 'font-size:0.8rem; color:#6a5a48; font-style:italic;';
  bidderEl.textContent = 'bid by ' + bidder;
  wrapper.appendChild(bidderEl);

  bidDisplay.innerHTML = '';
  bidDisplay.appendChild(wrapper);
}

// ============================================================
// SNAPSHOT RENDERER (full re-render from state)
// ============================================================
function renderSnapshot(snap) {
  lastSnapshot = snap;

  // Status bar
  const sb = $('status-bar');
  if (sb) {
    const totalDice = snap.active_players.reduce((s, p) => s + p.num_dice, 0);
    sb.innerHTML =
      `<span style="font-family:'Cinzel',serif; color:#c9a84c; font-weight:600;">Round ${snap.round_num}</span>` +
      `<span style="color:#3a3028;">·</span>` +
      `<span style="color:#7a6a58;">${totalDice} dice at sea</span>`;
  }

  renderRoster(snap);
  renderBid(snap);
}

// ============================================================
// HUMAN DICE
// ============================================================
function renderHumanDice() {
  const panel = $('human-dice');
  if (!panel) return;

  panel.innerHTML = '';
  if (!humanDice.length) {
    panel.innerHTML = '<span style="color:#4a4040; font-style:italic; font-size:0.85rem;">Awaiting the roll…</span>';
    return;
  }

  for (const face of humanDice) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('die-wrapper');
    wrapper.appendChild(makeDieSVG(face, 58));
    panel.appendChild(wrapper);
  }
}

// ============================================================
// EVENT FEED
// ============================================================
function addFeedEntry(html) {
  eventLog.unshift(html);
  if (eventLog.length > MAX_FEED_ITEMS) eventLog.length = MAX_FEED_ITEMS;
  renderFeed();
}

function renderFeed() {
  const feed = $('event-feed');
  if (!feed) return;

  const entries = eventLog.map((html, i) => {
    const opacity = Math.max(0.25, 1 - i * 0.09);
    const isNew = i === 0 ? 'feed-entry-new' : '';
    return `<div class="feed-entry ${isNew}" style="opacity:${opacity.toFixed(2)}">${html}</div>`;
  });
  feed.innerHTML = entries.join('');
}

function dieBadge(face) {
  return `<span class="inline-die-badge">${DICE_UNICODE[face] || face}</span>`;
}

// ============================================================
// ACTION PANEL
// ============================================================
function enableActions(request) {
  isHumanTurn    = true;
  currentRequest = request;

  const panel = $('action-panel');
  if (!panel) return;
  panel.classList.remove('disabled');

  const isOpening = request.type === 'opening_bid';

  $('bid-action-label').textContent = isOpening ? 'OPEN WITH' : 'RAISE TO';
  $('waiting-indicator').style.display = 'none';

  const challengeBtn = $('btn-challenge');
  const spotOnBtn    = $('btn-spot-on');

  if (isOpening) {
    setButtonDisabled(challengeBtn, true);
    setButtonDisabled(spotOnBtn, true);
  } else {
    setButtonDisabled(challengeBtn, false);
    setButtonDisabled(spotOnBtn, false);
  }

  // Pre-populate with a sensible raise
  if (!isOpening && request.prev_bid) {
    const { count, face } = request.prev_bid;
    const nextFace = face < 6 ? face + 1 : null;
    if (nextFace) {
      $('bid-count').value = count;
      setSelectedFace(nextFace);
    } else {
      $('bid-count').value = count + 1;
      setSelectedFace(1);
    }
  } else {
    $('bid-count').value = 2;
    const defaultFace = humanDice.length ? humanDice[0] : 1;
    setSelectedFace(defaultFace);
  }

  validateBidForm();

  // Scroll into view
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function disableActions() {
  isHumanTurn    = false;
  currentRequest = null;

  const panel = $('action-panel');
  if (!panel) return;
  panel.classList.add('disabled');

  setButtonDisabled($('btn-challenge'), true);
  setButtonDisabled($('btn-spot-on'),   true);
  setButtonDisabled($('btn-confirm-bid'), true);

  $('waiting-indicator').style.display = '';
}

function setButtonDisabled(btn, disabled) {
  if (!btn) return;
  btn.disabled = disabled;
  btn.classList.toggle('btn-disabled', disabled);
}

// ============================================================
// FACE SELECTOR
// ============================================================
function initFaceSelector() {
  const container = $('face-selector');
  if (!container) return;

  container.innerHTML = '';
  for (let f = 1; f <= 6; f++) {
    const btn = document.createElement('button');
    btn.className = 'face-btn';
    btn.dataset.face = f;
    btn.type = 'button';
    btn.appendChild(makeDieSVG(f, 38));
    btn.addEventListener('click', () => {
      setSelectedFace(f);
      validateBidForm();
    });
    container.appendChild(btn);
  }
  setSelectedFace(1);
}

function setSelectedFace(face) {
  selectedFace = face;
  document.querySelectorAll('.face-btn').forEach(btn => {
    btn.classList.toggle('face-btn-selected', parseInt(btn.dataset.face) === face);
  });
}

function validateBidForm() {
  const count = parseInt($('bid-count').value) || 0;
  const btn   = $('btn-confirm-bid');

  if (!isHumanTurn || !currentRequest || count < 1) {
    setButtonDisabled(btn, true);
    return;
  }

  if (currentRequest.type === 'decision' && currentRequest.prev_bid) {
    const { count: pc, face: pf } = currentRequest.prev_bid;
    const valid = count > pc || (count === pc && selectedFace > pf);
    setButtonDisabled(btn, !valid);
  } else {
    setButtonDisabled(btn, false);
  }
}

// ============================================================
// SEND ACTION
// ============================================================
function sendAction(action, bid) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ action, bid: bid || null }));
  disableActions();
}

// ============================================================
// ROLLS REVEAL OVERLAY
// ============================================================
function showRollsReveal(event) {
  const overlay  = $('rolls-reveal-overlay');
  const content  = $('rolls-reveal-content');
  if (!overlay || !content) return;

  const bidFace = event.bid_face;

  content.innerHTML = '';

  const title = document.createElement('h3');
  title.style.cssText = `
    font-family:'Cinzel',serif; font-size:1.4rem; color:#c9a84c;
    text-align:center; margin-bottom:1.5rem; letter-spacing:0.15em;
  `;
  title.textContent = '— CUPS LIFTED —';
  content.appendChild(title);

  const grid = document.createElement('div');
  grid.style.cssText = 'display:flex; flex-wrap:wrap; gap:20px; justify-content:center;';

  for (const player of (event.player_rolls || [])) {
    const col = document.createElement('div');
    col.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';

    const nameEl = document.createElement('div');
    nameEl.style.cssText = 'font-size:0.78rem; color:#8a7a68; text-align:center; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    nameEl.textContent = player.name;
    col.appendChild(nameEl);

    const diceRow = document.createElement('div');
    diceRow.style.cssText = 'display:flex; gap:4px; flex-wrap:wrap; justify-content:center;';

    for (const face of (player.dice || [])) {
      const wrapper = document.createElement('div');
      wrapper.classList.add('die-wrapper');
      if (face === bidFace || face === 1) wrapper.classList.add('die-highlight');
      wrapper.appendChild(makeDieSVG(face, 44));
      diceRow.appendChild(wrapper);
    }

    col.appendChild(diceRow);
    grid.appendChild(col);
  }

  content.appendChild(grid);
  overlay.classList.remove('hidden');

  // Auto-dismiss
  setTimeout(() => overlay.classList.add('hidden'), 3200);
}

// ============================================================
// GAME OVER OVERLAY
// ============================================================
function showGameOver(winner) {
  const overlay = $('gameover-overlay');
  if (!overlay) return;
  $('winner-name').textContent = winner || 'Unknown';
  overlay.classList.remove('hidden');
}

// ============================================================
// FLASH LOSER
// ============================================================
function flashLoser(name) {
  if (!name) return;
  document.querySelectorAll('.player-row').forEach(row => {
    if (row.dataset.playerName === name) {
      row.classList.remove('flash-red');
      void row.offsetWidth; // reflow to restart animation
      row.classList.add('flash-red');
    }
  });
}

// ============================================================
// MESSAGE HANDLER
// ============================================================
function handleMessage(data) {
  const { event, snapshot } = data;

  if (snapshot) renderSnapshot(snapshot);

  if (!event) return;
  const t = event.type;

  // ── Human input ──────────────────────────────────────────
  if (t === 'input_request') {
    const req = event.request;
    humanDice = req.dice || [];
    renderHumanDice();
    enableActions(req);
    addFeedEntry(`<span style="color:#c9a84c; font-family:'Cinzel',serif; font-size:0.8rem;">YOUR TURN</span>`);
    return;
  }

  // ── Bids ─────────────────────────────────────────────────
  if (t === 'bid_made') {
    addFeedEntry(`<b style="color:#d0c0a0">${escHtml(event.player_name)}</b> opens: ${event.count}× ${dieBadge(event.face)}`);
    return;
  }
  if (t === 'raise_made') {
    addFeedEntry(`<b style="color:#d0c0a0">${escHtml(event.player_name)}</b> raises to ${event.count}× ${dieBadge(event.face)}`);
    return;
  }

  // ── Challenges / Spot On ─────────────────────────────────
  if (t === 'challenge_called') {
    addFeedEntry(`⚔ <b style="color:#d0c0a0">${escHtml(event.challenger_name)}</b> calls out <b style="color:#d0c0a0">${escHtml(event.bidder_name)}</b>!`);
    return;
  }
  if (t === 'spot_on_called') {
    addFeedEntry(`🎯 <b style="color:#d0c0a0">${escHtml(event.caller_name)}</b> calls Spot On!`);
    return;
  }

  // ── Reveal ───────────────────────────────────────────────
  if (t === 'rolls_revealed') {
    showRollsReveal(event);
    return;
  }

  // ── Resolutions ──────────────────────────────────────────
  if (t === 'challenge_resolved') {
    const result = event.succeeded
      ? `<span style="color:#6da870;">Challenge succeeds</span>`
      : `<span style="color:#c06060;">Challenge fails</span>`;
    addFeedEntry(
      `${result} — ${event.actual_count}×${dieBadge(event.bid_face)} found. ` +
      `<b style="color:#d0c0a0;">${escHtml(event.loser_name)}</b> loses a die.`
    );
    flashLoser(event.loser_name);
    return;
  }
  if (t === 'spot_on_resolved') {
    const result = event.succeeded
      ? `<span style="color:#6da870;">Spot On hits!</span>`
      : `<span style="color:#c06060;">Spot On misses!</span>`;
    const losers = (event.loser_names || []).map(n => `<b style="color:#d0c0a0;">${escHtml(n)}</b>`).join(', ');
    addFeedEntry(`${result} ${losers} ${event.succeeded ? 'each ' : ''}lose a die.`);
    for (const n of event.loser_names || []) flashLoser(n);
    return;
  }

  // ── Eliminations ─────────────────────────────────────────
  if (t === 'player_eliminated') {
    addFeedEntry(`☠ <b style="color:#8a6060;">${escHtml(event.player_name)}</b> has fallen.`);
    return;
  }

  // ── Round lifecycle ──────────────────────────────────────
  if (t === 'round_started') {
    currentTurnPlayer = null;
    addFeedEntry(`<span style="color:#4a4040; font-family:'Cinzel',serif; font-size:0.78rem; letter-spacing:0.1em;">— ROUND ${event.round_num} —</span>`);
    disableActions();
    return;
  }
  if (t === 'turn_started') {
    currentTurnPlayer = event.player_name;
    if (lastSnapshot) renderRoster(lastSnapshot);
    return;
  }
  if (t === 'dice_rolled') {
    humanDice = [];
    const panel = $('human-dice');
    if (panel) panel.innerHTML = '<span style="color:#4a4040; font-style:italic; font-size:0.85rem;">Dice rolling…</span>';
    return;
  }
  if (t === 'human_turn_start') {
    // input_request follows immediately; do nothing here
    return;
  }

  // ── Game over ────────────────────────────────────────────
  if (t === 'game_won') {
    addFeedEntry(`🏆 <b style="color:#c9a84c; font-family:'Cinzel',serif;">${escHtml(event.winner_name)}</b> wins!`);
    showGameOver(event.winner_name);
    return;
  }
  if (t === 'session_ended') {
    // Sentinel; game_won already fired
    return;
  }
  if (t === 'round_summary') {
    // Snapshot already updated; no feed needed
    return;
  }

  // ── Errors ───────────────────────────────────────────────
  if (t === 'error') {
    console.warn('[game error]', event.func_name, event.message);
    return;
  }
}

// ============================================================
// WEBSOCKET
// ============================================================
function connect(sessionId) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url   = `${proto}//${location.host}/ws/${sessionId}`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    ws.send(JSON.stringify({
      type:        'join',
      human_name:  humanName,
      num_players: storedNumPlayers,
    }));
  };

  ws.onmessage = e => {
    try {
      handleMessage(JSON.parse(e.data));
    } catch (err) {
      console.error('WS parse error', err, e.data);
    }
  };

  ws.onerror = err => console.error('WebSocket error', err);
  ws.onclose = () => console.log('WebSocket closed');
}

// ============================================================
// LOBBY
// ============================================================
function initLobby() {
  const startBtn   = $('start-btn');
  const nameInput  = $('player-name');
  const numSelect  = $('num-players');
  const errMsg     = $('lobby-error');

  // Populate opponent count
  for (let total = 2; total <= MAX_PLAYERS; total++) {
    const opt = document.createElement('option');
    opt.value = total;
    opt.textContent = `${total - 1} opponent${total - 1 > 1 ? 's' : ''}`;
    numSelect.appendChild(opt);
  }
  numSelect.value = '3';

  startBtn.addEventListener('click', () => {
    const name = nameInput.value.trim();
    if (!name) {
      nameInput.classList.add('input-error');
      errMsg.classList.remove('hidden');
      nameInput.focus();
      return;
    }
    nameInput.classList.remove('input-error');
    errMsg.classList.add('hidden');

    humanName        = name;
    storedNumPlayers = parseInt(numSelect.value) || 3;
    startGame();
  });

  nameInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') startBtn.click();
  });
  nameInput.addEventListener('input', () => {
    nameInput.classList.remove('input-error');
    errMsg.classList.add('hidden');
  });
}

// ============================================================
// START GAME
// ============================================================
function startGame() {
  // Transition views
  $('lobby-view').style.display   = 'none';
  $('game-view').style.display    = 'flex';

  // Reset state
  humanDice         = [];
  isHumanTurn       = false;
  currentRequest    = null;
  currentTurnPlayer = null;
  eventLog          = [];
  lastSnapshot      = null;

  renderHumanDice();
  renderFeed();
  disableActions();

  const sessionId = crypto.randomUUID();
  connect(sessionId);
}

// ============================================================
// COIN DIAL (piece-of-eight opponent picker)
// ============================================================
function initCoinDial() {
  const numSelect  = $('num-players');
  const coinNumber = $('coin-number');
  const coinLabel  = $('coin-label');
  const coinWidget = $('coin-widget');
  const prevBtn    = $('coin-prev');
  const nextBtn    = $('coin-next');

  if (!numSelect || !coinWidget) return;

  function sync() {
    const total = parseInt(numSelect.value) || 3;
    const opp   = total - 1;
    coinNumber.textContent = opp;
    coinLabel.textContent  = opp === 1 ? 'OPPONENT' : 'OPPONENTS';
    prevBtn.disabled = total <= 2;
    nextBtn.disabled = total >= MAX_PLAYERS;
  }

  function tick(delta) {
    const v = parseInt(numSelect.value) || 3;
    const next = Math.min(Math.max(v + delta, 2), MAX_PLAYERS);
    if (next === v) return;
    numSelect.value = next;
    // Brief coin-spin animation
    coinWidget.classList.remove('coin-ticked');
    void coinWidget.offsetWidth; // force reflow to restart animation
    coinWidget.classList.add('coin-ticked');
    sync();
  }

  prevBtn.addEventListener('click', () => tick(-1));
  nextBtn.addEventListener('click', () => tick(+1));

  sync(); // align visual with whatever initLobby() set
}

// ============================================================
// PLAY AGAIN
// ============================================================
function initPlayAgain() {
  $('play-again-btn').addEventListener('click', () => {
    $('gameover-overlay').classList.add('hidden');
    $('rolls-reveal-overlay').classList.add('hidden');
    $('game-view').style.display  = 'none';
    $('lobby-view').style.display = 'flex';

    if (ws) { ws.close(); ws = null; }
  });
}

// ============================================================
// BID FORM WIRING
// ============================================================
function initBidForm() {
  $('bid-count').addEventListener('input', validateBidForm);

  $('btn-confirm-bid').addEventListener('click', () => {
    if (!isHumanTurn || !currentRequest) return;
    const count = parseInt($('bid-count').value);
    if (!count || count < 1) return;
    const action = currentRequest.type === 'opening_bid' ? 'BID' : 'RAISE';
    sendAction(action, { count, face: selectedFace });
  });

  $('btn-challenge').addEventListener('click', () => {
    if (!isHumanTurn || $('btn-challenge').disabled) return;
    sendAction('CHALLENGE', null);
  });

  $('btn-spot-on').addEventListener('click', () => {
    if (!isHumanTurn || $('btn-spot-on').disabled) return;
    sendAction('SPOT ON', null);
  });
}

// ============================================================
// XSS SAFETY
// ============================================================
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============================================================
// BOOT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  // Initial display state
  $('lobby-view').style.display  = 'flex';
  $('game-view').style.display   = 'none';

  initFaceSelector();
  initLobby();
  initCoinDial();
  initBidForm();
  initPlayAgain();
  disableActions();
});
