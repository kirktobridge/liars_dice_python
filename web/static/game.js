'use strict';

// ============================================================
// CONSTANTS
// ============================================================
const MAX_PLAYERS = 8;
const MAX_FEED_ITEMS = 10;

// PIP_POSITIONS and makeDieSVG live in dice.js, loaded before this script.

const DICE_UNICODE = { 1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅' };

const PLAYER_AVATARS = ['💀', '⚔️', '🗡️', '🔱', '🪝', '🧭', '🏴‍☠️', '⚡'];

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
let totalDiceInGame = 20;
let advisorData     = null;
let advisorEnabled  = false;
let humanEliminated = false;
let storedLlmModel  = '';
let llmThinkingFor  = null;  // player name currently "thinking" (LLM only)

// ============================================================
// DOM SHORTHAND
// ============================================================
const $ = id => document.getElementById(id);

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

  snap.active_players.forEach((p, idx) => {
    const isHuman   = p.player_type === 'HUMAN';
    const isCurrent = p.name === activeTurn;
    const isElim    = p.is_eliminated;

    const card = document.createElement('div');
    card.className = [
      'player-row',
      isHuman   ? 'player-row-human'  : '',
      isCurrent ? 'player-row-active' : '',
    ].filter(Boolean).join(' ');
    card.dataset.playerName = p.name;

    // Avatar emoji
    const avatar = document.createElement('div');
    avatar.className = 'player-card-avatar';
    avatar.textContent = isHuman ? '⚓' : PLAYER_AVATARS[idx % PLAYER_AVATARS.length];
    card.appendChild(avatar);

    // Name
    const nameEl = document.createElement('div');
    nameEl.className = 'player-card-name' +
      (isHuman && !isElim ? ' player-card-name-human' : '') +
      (isElim             ? ' player-card-name-elim'  : '');
    nameEl.textContent = p.name;
    card.appendChild(nameEl);

    // Turn indicator dot (only when active and alive)
    if (isCurrent && !isElim) {
      const dot = document.createElement('div');
      dot.className = 'player-card-turn pulse-dot';
      card.appendChild(dot);
    }

    // LLM "thinking…" indicator
    if (llmThinkingFor === p.name && !isElim) {
      const think = document.createElement('div');
      think.className = 'llm-thinking';
      think.innerHTML = '<span class="llm-spinner"></span><span class="llm-thinking-label">thinking…</span>';
      card.appendChild(think);
    }

    // Pip indicators
    const pipsEl = document.createElement('div');
    pipsEl.className = 'player-card-pips';
    if (isElim) {
      const x = document.createElement('span');
      x.className = 'player-card-elim-mark';
      x.textContent = '✗';
      pipsEl.appendChild(x);
    } else {
      for (let i = 0; i < p.num_dice; i++) {
        const pip = document.createElement('div');
        pip.className = 'player-card-pip' + (isHuman ? ' player-card-pip-human' : '');
        pipsEl.appendChild(pip);
      }
    }
    card.appendChild(pipsEl);

    roster.appendChild(card);
  });
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
function updateSliderFill() {
  const slider = $('bid-count');
  if (!slider) return;
  const min = parseInt(slider.min) || 1;
  const max = parseInt(slider.max) || 1;
  const val = parseInt(slider.value) || min;
  const pct = ((val - min) / (max - min) * 100).toFixed(1) + '%';
  slider.style.setProperty('--pct', pct);
}

function renderSnapshot(snap) {
  lastSnapshot = snap;

  // Status bar — update text span only so the ADVISOR button is preserved
  const sbText = $('status-bar-text');
  const totalDice = snap.active_players.reduce((s, p) => s + p.num_dice, 0);
  if (sbText) {
    sbText.innerHTML =
      `<span style="font-family:'Cinzel',serif; color:#c9a84c; font-weight:600;">Round ${snap.round_num}</span>` +
      `<span style="color:#3a3028; margin:0 0.4rem;">·</span>` +
      `<span style="color:#7a6a58;">${totalDice} dice at sea</span>`;
  }

  // Keep slider max in sync with total dice in game
  totalDiceInGame = totalDice;
  const slider = $('bid-count');
  if (slider) {
    slider.max = totalDice;
    if (parseInt(slider.value) > totalDice) {
      slider.value = totalDice;
      const disp = $('bid-count-display');
      if (disp) disp.textContent = totalDice;
    }
    updateSliderFill();
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

  const disp = $('bid-count-display');
  if (disp) disp.textContent = $('bid-count').value;
  updateSliderFill();

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
  advisorData = null;
  updateAdvisorDisplay();
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
      updateAdvisorBidProb();
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
  syncAdvisorBidHighlight();
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

  const bidFace  = event.bid_face;
  const bidCount = event.bid_count;

  content.innerHTML = '';

  const title = document.createElement('h3');
  title.style.cssText = `
    font-family:'Cinzel',serif; font-size:1.4rem; color:#c9a84c;
    text-align:center; margin-bottom:0.75rem; letter-spacing:0.15em;
  `;
  title.textContent = '— CUPS LIFTED —';
  content.appendChild(title);

  if (bidCount != null && bidFace != null) {
    const bidLine = document.createElement('div');
    bidLine.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:1.2rem; flex-wrap:wrap;';
    const bidLabel = document.createElement('span');
    bidLabel.style.cssText = 'font-family:"Cinzel",serif; font-size:0.85rem; color:#8a7a68; letter-spacing:0.1em;';
    if (event.bidder_name) {
      bidLabel.innerHTML = `bid by: <strong style="color:#d0c0a0;">${escHtml(event.bidder_name)}</strong>&ensp;<strong>${bidCount}</strong> ×`;
    } else {
      bidLabel.innerHTML = `BID: <strong>${bidCount}</strong> ×`;
    }
    bidLine.appendChild(bidLabel);
    const dieWrapper = document.createElement('div');
    dieWrapper.classList.add('die-wrapper');
    dieWrapper.appendChild(makeDieSVG(bidFace, 32));
    bidLine.appendChild(dieWrapper);
    content.appendChild(bidLine);
  }

  const grid = document.createElement('div');
  grid.style.cssText = 'display:flex; flex-wrap:wrap; gap:20px; justify-content:center;';

  for (const player of (event.player_rolls || [])) {
    const col = document.createElement('div');
    col.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:6px;';

    const nameEl = document.createElement('div');
    nameEl.style.cssText = 'font-size:0.82rem; font-weight:600; color:#c9b88a; text-align:center; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
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
  // outcome + close button added by resolveRollsReveal()
  overlay.classList.remove('hidden');
}

function resolveRollsReveal(succeeded, outcomeLabel, actualCount, onesCount, bidFace) {
  const overlay = $('rolls-reveal-overlay');
  const content = $('rolls-reveal-content');
  if (!overlay || !content) return;

  const actualLine = document.createElement('div');
  actualLine.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:wrap; margin-top:1rem;';

  const actualLabel = document.createElement('span');
  actualLabel.style.cssText = 'font-family:"Cinzel",serif; font-size:0.85rem; color:#8a7a68; letter-spacing:0.1em;';
  actualLabel.innerHTML = `ACTUAL: <strong>${actualCount}</strong> ×`;
  actualLine.appendChild(actualLabel);

  const dieWrapper2 = document.createElement('div');
  dieWrapper2.classList.add('die-wrapper');
  dieWrapper2.appendChild(makeDieSVG(bidFace, 32));
  actualLine.appendChild(dieWrapper2);

  if (bidFace !== 1 && onesCount > 0) {
    const plusLabel = document.createElement('span');
    plusLabel.style.cssText = 'font-family:"Cinzel",serif; font-size:0.85rem; color:#8a7a68;';
    plusLabel.innerHTML = `+ <strong>${onesCount}</strong> ×`;
    actualLine.appendChild(plusLabel);
    const onesWrapper = document.createElement('div');
    onesWrapper.classList.add('die-wrapper');
    onesWrapper.appendChild(makeDieSVG(1, 32));
    actualLine.appendChild(onesWrapper);
  }

  const effectiveTotal = (bidFace !== 1) ? actualCount + onesCount : actualCount;
  const eqSpan = document.createElement('span');
  eqSpan.style.cssText = 'font-family:"Cinzel",serif; font-size:0.85rem; color:#8a7a68;';
  eqSpan.innerHTML = `= <strong>${effectiveTotal}</strong>`;
  actualLine.appendChild(eqSpan);

  content.appendChild(actualLine);

  const verdict = document.createElement('div');
  verdict.style.cssText = `
    font-family:'Cinzel',serif; font-size:1.3rem; font-weight:bold;
    text-align:center; margin-top:0.9rem; letter-spacing:0.12em;
    color:${succeeded ? '#4caf6e' : '#c06060'};
  `;
  verdict.textContent = outcomeLabel;
  content.appendChild(verdict);

  if (humanEliminated) {
    setTimeout(() => {
      overlay.classList.add('hidden');
      if (ws) ws.send(JSON.stringify({ type: 'rolls_revealed_ack' }));
    }, 5000);
  } else {
    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Lower Cups';
    closeBtn.style.cssText = `
      display:block; margin:1.5rem auto 0;
      background:#7c4f1e; color:#f5e6c8; border:1px solid #c9a84c;
      font-family:'Cinzel',serif; font-size:0.9rem; letter-spacing:0.1em;
      padding:0.5rem 1.8rem; border-radius:6px; cursor:pointer;
    `;
    closeBtn.onclick = () => {
      overlay.classList.add('hidden');
      if (ws) ws.send(JSON.stringify({ type: 'rolls_revealed_ack' }));
    };
    content.appendChild(closeBtn);
  }
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
    advisorData = event.advisor || null;
    enableActions(req);
    updateAdvisorDisplay();
    addFeedEntry(`<span style="color:#c9a84c; font-family:'Cinzel',serif; font-size:0.8rem;">YOUR TURN</span>`);
    return;
  }

  // ── Bids ─────────────────────────────────────────────────
  if (t === 'bid_made') {
    if (llmThinkingFor === event.player_name) llmThinkingFor = null;
    addFeedEntry(`<b style="color:#d0c0a0">${escHtml(event.player_name)}</b> opens: ${event.count}× ${dieBadge(event.face)}`);
    return;
  }
  if (t === 'raise_made') {
    if (llmThinkingFor === event.player_name) llmThinkingFor = null;
    addFeedEntry(`<b style="color:#d0c0a0">${escHtml(event.player_name)}</b> raises to ${event.count}× ${dieBadge(event.face)}`);
    return;
  }

  // ── Challenges / Spot On ─────────────────────────────────
  if (t === 'challenge_called') {
    if (llmThinkingFor === event.challenger_name) llmThinkingFor = null;
    disableActions();
    addFeedEntry(`⚔ <b style="color:#d0c0a0">${escHtml(event.challenger_name)}</b> calls out <b style="color:#d0c0a0">${escHtml(event.bidder_name)}</b>!`);
    return;
  }
  if (t === 'spot_on_called') {
    if (llmThinkingFor === event.caller_name) llmThinkingFor = null;
    disableActions();
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
    const outcomeLabel = event.succeeded ? 'CORRECT CALL' : 'FAILURE';
    resolveRollsReveal(event.succeeded, outcomeLabel, event.actual_count, event.ones_count, event.bid_face);
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
    const outcomeLabel = event.succeeded ? 'CORRECT CALL' : 'FAILURE';
    resolveRollsReveal(event.succeeded, outcomeLabel, event.actual_count, event.ones_count, event.bid_face);
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
    if (event.player_type === 'HUMAN') {
      humanEliminated = true;
      const elOverlay = $('rolls-reveal-overlay');
      if (elOverlay && !elOverlay.classList.contains('hidden')) {
        setTimeout(() => {
          elOverlay.classList.add('hidden');
          if (ws) ws.send(JSON.stringify({ type: 'rolls_revealed_ack' }));
        }, 2000);
      }
    }
    return;
  }

  // ── Round lifecycle ──────────────────────────────────────
  if (t === 'round_started') {
    currentTurnPlayer = null;
    llmThinkingFor = null;
    addFeedEntry(`<span style="color:#4a4040; font-family:'Cinzel',serif; font-size:0.78rem; letter-spacing:0.1em;">— ROUND ${event.round_num} —</span>`);
    disableActions();
    return;
  }
  if (t === 'turn_started') {
    currentTurnPlayer = event.player_name;
    llmThinkingFor = event.player_type === 'LLM' ? event.player_name : null;
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
      llm_model:   storedLlmModel || null,
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
    const llmSelect  = $('llm-model');
    storedLlmModel   = llmSelect ? llmSelect.value : '';
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
  humanEliminated   = false;
  llmThinkingFor    = null;
  totalDiceInGame   = storedNumPlayers * 5;
  const slider = $('bid-count');
  if (slider) { slider.max = totalDiceInGame; slider.value = 2; }
  const disp = $('bid-count-display');
  if (disp) disp.textContent = '2';
  updateSliderFill();

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

  let current = parseInt(numSelect.value) || 3;

  function sync() {
    const opp = current - 1;
    coinNumber.textContent = opp;
    coinLabel.textContent  = opp === 1 ? 'OPPONENT' : 'OPPONENTS';
    prevBtn.disabled = current <= 2;
    nextBtn.disabled = current >= MAX_PLAYERS;
    numSelect.value  = String(current);
  }

  function tick(delta) {
    const next = Math.min(Math.max(current + delta, 2), MAX_PLAYERS);
    if (next === current) return;
    current = next;
    sync();
    coinWidget.classList.remove('coin-ticked');
    void coinWidget.offsetWidth;
    coinWidget.classList.add('coin-ticked');
    coinWidget.addEventListener('animationend', () => coinWidget.classList.remove('coin-ticked'), { once: true });
  }

  prevBtn.addEventListener('click', () => tick(-1));
  nextBtn.addEventListener('click', () => tick(+1));

  coinWidget.addEventListener('wheel', (e) => {
    e.preventDefault();
    tick(e.deltaY > 0 ? -1 : 1);
  }, { passive: false });

  sync();
}

// ============================================================
// LLM OPPONENT DROPDOWN
// ============================================================
async function fetchLlmModels() {
  const resp = await fetch('/llm/models');
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}

function renderLlmOpponent(data) {
  const select   = $('llm-model');
  const startBtn = $('llm-start-btn');
  const hint     = $('llm-hint');
  if (!select || !startBtn) return;

  // Reset
  select.innerHTML = '<option value="">None — all CPU</option>';
  select.disabled = false;

  if (!data.available) {
    select.style.display = 'none';
    startBtn.style.display = '';
    if (hint) hint.textContent = 'Ollama is not running.';
    return;
  }

  startBtn.style.display = 'none';
  select.style.display = '';

  if (!Array.isArray(data.models) || data.models.length === 0) {
    select.disabled = true;
    if (hint) hint.textContent = 'Ollama is running but has no models installed.';
    return;
  }

  for (const name of data.models) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  }
  if (hint) hint.textContent = 'One opponent will be powered by the chosen LLM.';
}

async function initLlmOpponent() {
  const row      = $('llm-opponent-row');
  const startBtn = $('llm-start-btn');
  const hint     = $('llm-hint');
  if (!row || !startBtn) return;

  startBtn.addEventListener('click', async () => {
    startBtn.disabled = true;
    const original = startBtn.textContent;
    startBtn.textContent = 'STARTING…';
    if (hint) hint.textContent = 'Spawning ollama serve…';
    try {
      const resp = await fetch('/llm/start', { method: 'POST' });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail.detail || ('HTTP ' + resp.status));
      }
      const data = await fetchLlmModels();
      renderLlmOpponent(data);
    } catch (err) {
      console.warn('Ollama start failed', err);
      startBtn.disabled = false;
      startBtn.textContent = original;
      if (hint) hint.textContent = 'Failed to start Ollama: ' + err.message;
    }
  });

  let data;
  try {
    data = await fetchLlmModels();
  } catch (err) {
    console.warn('LLM models lookup failed', err);
    data = { available: false, models: [] };
  }
  renderLlmOpponent(data);
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
  $('bid-count').addEventListener('input', () => {
    const disp = $('bid-count-display');
    if (disp) disp.textContent = $('bid-count').value;
    updateSliderFill();
    validateBidForm();
    updateAdvisorBidProb();
    syncAdvisorBidHighlight();
  });

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
// ADVISOR MODE
// ============================================================
function updateAdvisorToggle() {
  const btn = $('btn-advisor-toggle');
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(advisorEnabled));
  btn.classList.toggle('advisor-toggle-on', advisorEnabled);
  document.body.classList.toggle('advisor-active', advisorEnabled);
}

function syncAdvisorBidHighlight() {
  const count = String($('bid-count').value);
  const face  = String(selectedFace);
  document.querySelectorAll('.advisor-bid-row').forEach(row => {
    const sel = row.dataset.count === count && row.dataset.face === face;
    row.classList.toggle('selected', sel);
    const star = row.querySelector('.advisor-bid-star');
    if (star) star.textContent = sel ? '★' : '';
  });
}

function _selectedBidProb() {
  if (!advisorData || !advisorData.bid_probs) return null;
  const faceKey  = String(selectedFace);
  const countKey = String($('bid-count').value);
  return advisorData.bid_probs[faceKey]?.[countKey] ?? null;
}

function updateAdvisorBidProb() {
  const span = $('advisor-bid-prob');
  if (span) {
    const prob = _selectedBidProb();
    if (prob !== null && advisorEnabled && isHumanTurn) {
      const pct  = Math.round(prob * 100);
      const tier = prob >= 0.6 ? 'bar-high' : prob >= 0.3 ? 'bar-mid' : 'bar-low';
      span.textContent = pct + '% TRUE';
      span.className = `advisor-prob ${tier}`;
    } else {
      span.textContent = '';
      span.className = 'advisor-prob';
    }
  }
  syncAdvisorBidHighlight();
}

function buildAdvisorPanel() {
  const panel       = $('advisor-panel');
  const actionsNote = $('advisor-actions-note');
  if (!panel) return;

  if (!advisorData || !isHumanTurn || !currentRequest) {
    panel.innerHTML = '';
    if (actionsNote) actionsNote.textContent = '';
    return;
  }

  panel.innerHTML = '';
  if (actionsNote) actionsNote.textContent = '';

  // ── Block 1: Situation Bar ──────────────────────────────────
  const oppDice   = currentRequest.tot_other_dice || 0;
  const yourDice  = humanDice.length;
  const totalDice = oppDice + yourDice;

  const situLabel = document.createElement('div');
  situLabel.className = 'advisor-section-label';
  situLabel.textContent = 'SITUATION';
  panel.appendChild(situLabel);

  const statRow = document.createElement('div');
  statRow.className = 'advisor-stat-row';
  for (const { value, label } of [
    { value: totalDice, label: 'TOTAL' },
    { value: oppDice,   label: 'OPP. DICE' },
    { value: yourDice,  label: 'YOUR DICE' },
  ]) {
    const box = document.createElement('div');
    box.className = 'advisor-stat-box';
    const valEl = document.createElement('div');
    valEl.className = 'advisor-stat-value';
    valEl.textContent = value;
    const lblEl = document.createElement('div');
    lblEl.className = 'advisor-stat-label';
    lblEl.textContent = label;
    box.appendChild(valEl);
    box.appendChild(lblEl);
    statRow.appendChild(box);
  }
  panel.appendChild(statRow);

  // ── Block 2: Bid Assessment (decision only) ─────────────────
  const prevBid = currentRequest.prev_bid;
  if (currentRequest.type === 'decision' && prevBid) {
    const assessLabel = document.createElement('div');
    assessLabel.className = 'advisor-section-label';
    assessLabel.textContent = 'BID ASSESSMENT';
    panel.appendChild(assessLabel);

    const assess = document.createElement('div');
    assess.className = 'advisor-assessment';

    const bidFace = prevBid.face;
    const ownCount = humanDice.reduce((n, d) => {
      if (d === bidFace) return n + 1;
      if (bidFace !== 1 && d === 1) return n + 1;
      return n;
    }, 0);
    const needed = prevBid.count - ownCount;
    const neededText = needed <= 0
      ? 'you already cover it'
      : `${needed} still needed from ${oppDice} opp. dice`;

    const note = document.createElement('div');
    note.className = 'advisor-assessment-note';
    note.textContent = `You hold: ${ownCount} matching · ${neededText}`;
    assess.appendChild(note);

    if (actionsNote) actionsNote.textContent = note.textContent;

    const chProb   = advisorData.challenge_prob  || 0;
    const soProb   = advisorData.spot_on_prob     || 0;
    const bidHolds = Math.max(0, 1 - chProb - soProb);

    for (const { label, prob } of [
      { label: 'CHALLENGE',  prob: chProb   },
      { label: 'SPOT ON',    prob: soProb   },
      { label: 'BID HOLDS',  prob: bidHolds },
    ]) {
      const pct  = Math.round(prob * 100);
      const tier = prob >= 0.6 ? 'bar-high' : prob >= 0.3 ? 'bar-mid' : 'bar-low';

      const probRow = document.createElement('div');
      probRow.className = 'advisor-prob-row';

      const labelEl = document.createElement('div');
      labelEl.className = 'advisor-prob-row-label';
      labelEl.textContent = label;

      const track = document.createElement('div');
      track.className = 'advisor-prob-bar-track';
      const fill = document.createElement('div');
      fill.className = `advisor-prob-bar-fill ${tier}`;
      fill.style.width = pct + '%';
      track.appendChild(fill);

      const pctEl = document.createElement('div');
      pctEl.className = `advisor-prob-pct ${tier}`;
      pctEl.textContent = pct + '%';

      probRow.appendChild(labelEl);
      probRow.appendChild(track);
      probRow.appendChild(pctEl);
      assess.appendChild(probRow);
    }

    panel.appendChild(assess);
  }

  // ── Block 3: Top Bids Table ─────────────────────────────────
  const bidsLabel = document.createElement('div');
  bidsLabel.className = 'advisor-section-label';
  bidsLabel.textContent = 'TOP BIDS';
  panel.appendChild(bidsLabel);

  const entries = [];
  if (advisorData.bid_probs) {
    for (const [face, counts] of Object.entries(advisorData.bid_probs)) {
      for (const [count, prob] of Object.entries(counts)) {
        entries.push({ face: parseInt(face), count: parseInt(count), prob });
      }
    }
  }
  entries.sort((a, b) => b.prob - a.prob);

  const currentCount = String($('bid-count').value);
  const currentFace  = String(selectedFace);

  const selInTop5 = entries.slice(0, 5).some(
    e => String(e.count) === currentCount && String(e.face) === currentFace
  );
  const selProb = !selInTop5
    ? (advisorData.bid_probs?.[currentFace]?.[currentCount] ?? null)
    : null;

  const table = document.createElement('div');
  table.className = 'advisor-bids-table';

  if (selProb !== null) {
    const pct  = Math.round(selProb * 100);
    const tier = selProb >= 0.6 ? 'bar-high' : selProb >= 0.3 ? 'bar-mid' : 'bar-low';
    const row  = document.createElement('div');
    row.className = 'advisor-bid-row selected pinned';
    row.dataset.count = currentCount;
    row.dataset.face  = currentFace;

    const bidLabel = document.createElement('div');
    bidLabel.className = 'advisor-bid-label';
    bidLabel.textContent = `${currentCount}× ${DICE_UNICODE[parseInt(currentFace)] || currentFace}`;

    const track = document.createElement('div');
    track.className = 'advisor-prob-bar-track';
    track.style.flex = '1';
    const fill = document.createElement('div');
    fill.className = `advisor-prob-bar-fill ${tier}`;
    fill.style.width = pct + '%';
    track.appendChild(fill);

    const pctEl = document.createElement('div');
    pctEl.className = 'advisor-bid-pct';
    pctEl.textContent = pct + '%';

    const star = document.createElement('div');
    star.className = 'advisor-bid-star';
    star.textContent = '★';

    row.appendChild(bidLabel);
    row.appendChild(track);
    row.appendChild(pctEl);
    row.appendChild(star);
    table.appendChild(row);
  }

  for (const { face, count, prob } of entries.slice(0, 5)) {
    const pct  = Math.round(prob * 100);
    const tier = prob >= 0.6 ? 'bar-high' : prob >= 0.3 ? 'bar-mid' : 'bar-low';
    const isSel = String(count) === currentCount && String(face) === currentFace;

    const row = document.createElement('div');
    row.className = 'advisor-bid-row' + (isSel ? ' selected' : '');
    row.dataset.count = String(count);
    row.dataset.face  = String(face);

    const bidLabel = document.createElement('div');
    bidLabel.className = 'advisor-bid-label';
    bidLabel.textContent = `${count}× ${DICE_UNICODE[face] || face}`;

    const track = document.createElement('div');
    track.className = 'advisor-prob-bar-track';
    track.style.flex = '1';
    const fill = document.createElement('div');
    fill.className = `advisor-prob-bar-fill ${tier}`;
    fill.style.width = pct + '%';
    track.appendChild(fill);

    const pctEl = document.createElement('div');
    pctEl.className = 'advisor-bid-pct';
    pctEl.textContent = pct + '%';

    const star = document.createElement('div');
    star.className = 'advisor-bid-star';
    star.textContent = isSel ? '★' : '';

    row.appendChild(bidLabel);
    row.appendChild(track);
    row.appendChild(pctEl);
    row.appendChild(star);

    row.addEventListener('click', () => {
      $('bid-count').value = count;
      const disp = $('bid-count-display');
      if (disp) disp.textContent = count;
      updateSliderFill();
      setSelectedFace(face);
      validateBidForm();
      updateAdvisorBidProb();
    });

    table.appendChild(row);
  }
  panel.appendChild(table);
}

function updateAdvisorDisplay() {
  const challengeSpan = $('advisor-challenge-prob');
  const spotOnSpan    = $('advisor-spot-on-prob');
  if (challengeSpan) challengeSpan.textContent = '';
  if (spotOnSpan)    spotOnSpan.textContent    = '';
  updateAdvisorBidProb();
  buildAdvisorPanel();
}

function initAdvisorToggle() {
  const btn = $('btn-advisor-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    advisorEnabled = !advisorEnabled;
    updateAdvisorToggle();
    updateAdvisorDisplay();
  });
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
  initAdvisorToggle();
  initLlmOpponent();
  disableActions();
  updateSliderFill();
});
