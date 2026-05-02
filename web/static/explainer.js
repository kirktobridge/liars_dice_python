'use strict';

const FACE_NAMES = { 1: 'ones', 2: 'twos', 3: 'threes', 4: 'fours', 5: 'fives', 6: 'sixes' };

const $ = id => document.getElementById(id);

let currentResult = null;
let currentStepIdx = 0;

function el(tag, classes, text) {
  const node = document.createElement(tag);
  if (classes) node.className = classes;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function fmtPct(value) {
  return (value * 100).toFixed(0) + '%';
}

function fmtNum(value, dp = 2) {
  return Number(value).toFixed(dp);
}

// ============================================================
// PICKER
// ============================================================
async function loadPicker() {
  const res = await fetch('/explainer/scenarios');
  const data = await res.json();
  const grid = $('picker-cards');
  grid.innerHTML = '';
  for (const s of data.scenarios) {
    const card = el('button', 'picker-card');
    card.dataset.scenarioId = s.id;
    card.appendChild(el('div', 'picker-card-title', s.title));
    card.appendChild(el('div', 'picker-card-summary', s.summary));
    card.addEventListener('click', () => loadScenario(s.id));
    grid.appendChild(card);
  }
}

async function loadScenario(scenarioId) {
  const res = await fetch(`/explainer/scenario/${encodeURIComponent(scenarioId)}`);
  if (!res.ok) {
    console.error('Failed to load scenario', scenarioId, res.status);
    return;
  }
  currentResult = await res.json();
  currentStepIdx = 0;
  $('picker-section').classList.add('hidden');
  $('step-section').classList.remove('hidden');
  renderScenarioHeader();
  renderStep();
}

function backToPicker() {
  $('step-section').classList.add('hidden');
  $('picker-section').classList.remove('hidden');
  currentResult = null;
}

// ============================================================
// STEP RENDERING
// ============================================================
function renderScenarioHeader() {
  const scn = currentResult.scenario;
  $('step-scenario-title').textContent = scn.title;
  $('step-scenario-intro').textContent = scn.narrative_intro;

  const dots = $('progress-dots');
  dots.innerHTML = '';
  for (let i = 0; i < currentResult.steps.length; i++) {
    const d = el('span', 'progress-dot');
    if (i === currentStepIdx) d.classList.add('progress-dot-active');
    if (i < currentStepIdx) d.classList.add('progress-dot-done');
    dots.appendChild(d);
  }
}

function renderStep() {
  const step = currentResult.steps[currentStepIdx];
  $('step-title').textContent = step.title;
  $('step-narrative').textContent = step.narrative;

  const dataPanel = $('step-data');
  dataPanel.innerHTML = '';
  switch (step.step_id) {
    case 'roll':         renderRollStep(dataPanel, step); break;
    case 'stats':        renderStatsStep(dataPanel, step); break;
    case 'evaluate-bid': renderEvalBidStep(dataPanel, step); break;
    case 'context':      renderContextStep(dataPanel, step); break;
    case 'personality':  renderPersonalityStep(dataPanel, step); break;
    case 'decision':     renderDecisionStep(dataPanel, step); break;
  }

  $('step-counter').textContent = `STEP ${currentStepIdx + 1} OF ${currentResult.steps.length}`;
  $('btn-prev').disabled = currentStepIdx === 0;
  $('btn-next').disabled = currentStepIdx === currentResult.steps.length - 1;

  // Update progress dots
  const dots = $('progress-dots').children;
  for (let i = 0; i < dots.length; i++) {
    dots[i].className = 'progress-dot';
    if (i === currentStepIdx) dots[i].classList.add('progress-dot-active');
    else if (i < currentStepIdx) dots[i].classList.add('progress-dot-done');
  }
}

// ── step 1: roll
function renderRollStep(panel, step) {
  const wrap = el('div', 'roll-wrap');
  const diceRow = el('div', 'dice-row');
  for (const face of step.data.dice) {
    diceRow.appendChild(makeDieSVG(face, 56));
  }
  wrap.appendChild(diceRow);

  const meta = el('div', 'roll-meta');
  meta.appendChild(makeStatBox('CPU dice', String(step.data.num_dice)));
  meta.appendChild(makeStatBox('Other dice', String(step.data.tot_other_dice)));
  meta.appendChild(makeStatBox('Total in play', String(step.data.total_dice)));
  wrap.appendChild(meta);

  panel.appendChild(wrap);
}

// ── step 2: stats
function renderStatsStep(panel, step) {
  const wrap = el('div', 'stats-wrap');
  const dieWrap = el('div', 'mode-die');
  dieWrap.appendChild(makeDieSVG(step.data.mode_face, 80));
  dieWrap.appendChild(el('div', 'mode-label', `most common (${FACE_NAMES[step.data.mode_face]})`));
  wrap.appendChild(dieWrap);

  const meta = el('div', 'stats-meta');
  meta.appendChild(makeStatBox('Mode face', String(step.data.mode_face)));
  meta.appendChild(makeStatBox('Mode count (incl. wilds)', String(step.data.mode_count)));
  wrap.appendChild(meta);

  panel.appendChild(wrap);
}

// ── step 3: evaluate-bid
function renderEvalBidStep(panel, step) {
  const wrap = el('div', 'eval-wrap');
  const bidRow = el('div', 'bid-display-row');
  bidRow.appendChild(el('div', 'bid-label', `${step.data.prev_bidder} claims:`));
  const bidShow = el('div', 'bid-show');
  bidShow.appendChild(el('span', 'bid-count', String(step.data.prev_bid_count)));
  bidShow.appendChild(makeDieSVG(step.data.prev_bid_face, 48));
  bidRow.appendChild(bidShow);
  wrap.appendChild(bidRow);

  const meta = el('div', 'eval-meta');
  meta.appendChild(makeStatBox('Need from others', String(step.data.needed_cnt)));
  const branchLabel = step.data.auto_raise_short_circuit
    ? 'Auto-raise (hand alone covers bid)'
    : 'Continue evaluating';
  meta.appendChild(makeStatBox('Path', branchLabel));
  wrap.appendChild(meta);

  panel.appendChild(wrap);
}

// ── step 4: context
function renderContextStep(panel, step) {
  // Replace the dense paragraph with a short orienting line.
  $('step-narrative').textContent =
    'Four independent lenses on the previous bid. Each one is computed from raw inputs (bid, dice counts, observed history) and feeds Step 5.';

  const d = step.data;
  const wrap = el('div', 'context-wrap');

  // Lens 1 — Probabilities
  const probBlock = makeContextBlock('Lens 1 · Probabilities',
    'How likely is the bid true, exactly correct, or beatable by the CPU\'s best legal raise?');
  const gaugeGrid = el('div', 'gauge-grid');
  gaugeGrid.appendChild(makeGaugeCard('Challenge probability', d.challenge_prob,
    'P(bid is a lie) — binomial over unseen dice.'));
  gaugeGrid.appendChild(makeGaugeCard('Spot-on probability', d.spot_on_prob,
    `P(exact count) → EV ${fmtNum(d.spot_on_ev, 2)} dice with ${d.num_active_players} players.`));
  gaugeGrid.appendChild(makeGaugeCard('Best legal bid', d.best_bid_prob,
    `Strongest legal bid: ${d.best_bid_desc}.`));
  gaugeGrid.appendChild(makeGaugeCard('Effective threshold', d.effective_threshold,
    'Break-even floor (0.50). Higher = more confidence demanded.'));
  probBlock.appendChild(gaugeGrid);
  wrap.appendChild(probBlock);

  // Lens 2 — Blind Aggression Score (derivation map)
  const basBlock = makeContextBlock('Lens 2 · Blind Aggression Score',
    'Did the bidder claim more dice than their own information justifies?');
  basBlock.appendChild(makeBASMap(d));
  wrap.appendChild(basBlock);

  // Lens 3 — Opponent profile (only if observations exist)
  if (d.opponent_bids_observed > 0) {
    const profBlock = makeContextBlock('Lens 3 · Opponent Profile',
      'A running history of this bidder, built up by every prior bid the CPU has witnessed.');
    profBlock.appendChild(makeProfileMap(d));
    wrap.appendChild(profBlock);
  }

  // Lens 4 — Pressure-opportunity
  const pressBlock = makeContextBlock('Lens 4 · Pressure-Opportunity',
    'How squeezable is the next player? Combines their dice count with escalation room.');
  const pressRow = el('div', 'press-row');
  pressRow.appendChild(makeStatBox('Score', fmtNum(d.pressure_opportunity_score)));
  pressRow.appendChild(el('div', 'press-caption font-body',
    'Above 0.45 (with cunning) tilts bid selection toward the higher-count raise → feeds Step 6.'));
  pressBlock.appendChild(pressRow);
  wrap.appendChild(pressBlock);

  panel.appendChild(wrap);
}

// Red (0%) → yellow (50%) → green (100%). HSL hue 0..120.
function gaugeColor(value) {
  const v = Math.max(0, Math.min(1, value));
  const hue = v * 120;
  return `hsl(${hue}, 75%, 50%)`;
}

function makeGaugeCard(label, value, caption) {
  const v = Math.max(0, Math.min(1, value));
  const color = gaugeColor(v);

  const card = el('div', 'gauge-card');
  card.appendChild(el('div', 'gauge-card-label', label));

  // SVG semicircle gauge. Arc length = π·r. We trace from left (180°) to right (0°).
  const W = 160, H = 92, CX = 80, CY = 82, R = 64;
  const STROKE = 14;
  const arcLen = Math.PI * R;

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('class', 'gauge-svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);

  // Background track
  const bg = document.createElementNS(svgNS, 'path');
  bg.setAttribute('d', `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`);
  bg.setAttribute('fill', 'none');
  bg.setAttribute('stroke', 'rgba(255,255,255,0.08)');
  bg.setAttribute('stroke-width', STROKE);
  bg.setAttribute('stroke-linecap', 'round');
  svg.appendChild(bg);

  // Foreground arc
  const fg = document.createElementNS(svgNS, 'path');
  fg.setAttribute('d', `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`);
  fg.setAttribute('fill', 'none');
  fg.setAttribute('stroke', color);
  fg.setAttribute('stroke-width', STROKE);
  fg.setAttribute('stroke-linecap', 'round');
  fg.setAttribute('stroke-dasharray', `${arcLen}`);
  fg.setAttribute('stroke-dashoffset', `${arcLen * (1 - v)}`);
  fg.style.transition = 'stroke-dashoffset 480ms ease, stroke 480ms ease';
  svg.appendChild(fg);

  // Tick marks at 0%, 50%, 100% positions on the arc
  for (const t of [0, 0.5, 1]) {
    const ang = Math.PI - t * Math.PI; // 180° → 0°
    const x1 = CX + (R - STROKE / 2 - 4) * Math.cos(ang);
    const y1 = CY - (R - STROKE / 2 - 4) * Math.sin(ang);
    const x2 = CX + (R + STROKE / 2 + 2) * Math.cos(ang);
    const y2 = CY - (R + STROKE / 2 + 2) * Math.sin(ang);
    const tick = document.createElementNS(svgNS, 'line');
    tick.setAttribute('x1', x1); tick.setAttribute('y1', y1);
    tick.setAttribute('x2', x2); tick.setAttribute('y2', y2);
    tick.setAttribute('stroke', 'rgba(255,255,255,0.18)');
    tick.setAttribute('stroke-width', 1);
    svg.appendChild(tick);
  }

  card.appendChild(svg);

  const pct = el('div', 'gauge-pct', fmtPct(v));
  pct.style.color = color;
  pct.style.textShadow = `0 0 12px ${color}`;
  card.appendChild(pct);

  if (caption) card.appendChild(el('div', 'gauge-caption', caption));
  return card;
}

function makeContextBlock(title, subtitle) {
  const block = el('div', 'context-block');
  block.appendChild(el('div', 'context-block-title', title));
  if (subtitle) block.appendChild(el('div', 'context-block-subtitle', subtitle));
  return block;
}

function makeBASMap(d) {
  const map = el('div', 'calc-map');

  const branches = el('div', 'calc-branches');

  // Left branch — bid_ratio
  const left = el('div', 'calc-branch');
  left.appendChild(makeCalcInputs([
    { label: 'Bid count', value: d.prev_bid_count },
    { label: 'Total dice', value: d.total_dice },
  ]));
  left.appendChild(el('div', 'calc-arrow', '↓'));
  left.appendChild(makeCalcDerived('bid_ratio',
    `${d.prev_bid_count} ÷ ${d.total_dice}`, fmtPct(d.bid_count_ratio)));

  // Right branch — info_ratio
  const right = el('div', 'calc-branch');
  right.appendChild(makeCalcInputs([
    { label: 'Bidder dice', value: d.bidder_num_dice },
    { label: 'Total dice', value: d.total_dice },
  ]));
  right.appendChild(el('div', 'calc-arrow', '↓'));
  right.appendChild(makeCalcDerived('info_ratio',
    `${d.bidder_num_dice} ÷ ${d.total_dice}`, fmtPct(d.bidder_info_ratio)));

  branches.appendChild(left);
  branches.appendChild(el('div', 'calc-divider', '÷'));
  branches.appendChild(right);
  map.appendChild(branches);

  map.appendChild(el('div', 'calc-arrow calc-arrow-merge', '↓'));

  // Final BAS card
  const bas = el('div', 'calc-final');
  bas.appendChild(el('div', 'calc-final-label', 'Blind Aggression Score'));
  bas.appendChild(el('div', 'calc-final-formula',
    `${fmtPct(d.bid_count_ratio)} ÷ ${fmtPct(d.bidder_info_ratio)}`));
  bas.appendChild(el('div', 'calc-final-value', fmtNum(d.blind_aggression_score)));
  const above = d.blind_aggression_score > d.blind_aggression_threshold;
  const flag = el('div', 'calc-final-flag',
    above
      ? `▲ above threshold ${fmtNum(d.blind_aggression_threshold)} — over-claiming`
      : `▼ at or below threshold ${fmtNum(d.blind_aggression_threshold)}`);
  if (above) flag.classList.add('calc-flag-hot');
  bas.appendChild(flag);
  map.appendChild(bas);

  map.appendChild(el('div', 'calc-downstream',
    above
      ? '→ Step 5: cunning amplifies challenge probability and lowers the threshold'
      : '→ Step 5: no challenge boost applied'));

  return map;
}

function makeProfileMap(d) {
  const map = el('div', 'profile-map');

  const aggRow = el('div', 'profile-row');
  aggRow.appendChild(makeCalcInputs([
    { label: 'Bids observed', value: d.opponent_bids_observed },
  ]));
  aggRow.appendChild(el('div', 'calc-arrow-h', '→'));
  aggRow.appendChild(makeCalcDerived('Avg aggression', null,
    d.opponent_avg_aggression !== null ? fmtNum(d.opponent_avg_aggression) : '—'));
  map.appendChild(aggRow);

  if (d.opponent_bids_challenged > 0) {
    const bluffRow = el('div', 'profile-row');
    bluffRow.appendChild(makeCalcInputs([
      { label: 'Challenged', value: d.opponent_bids_challenged },
      { label: 'Successful', value: d.opponent_challenge_successes },
    ]));
    bluffRow.appendChild(el('div', 'calc-arrow-h', '→'));
    bluffRow.appendChild(makeCalcDerived('Bluff rate (smoothed)', null,
      d.opponent_bluff_rate !== null ? fmtPct(d.opponent_bluff_rate) : '—'));
    map.appendChild(bluffRow);
    map.appendChild(el('div', 'calc-downstream',
      '→ Step 5: lowers challenge threshold for this bidder'));
  } else {
    map.appendChild(el('div', 'calc-downstream',
      '→ Step 5: aggression boost only (no challenge history yet)'));
  }

  return map;
}

function makeCalcInputs(items) {
  const wrap = el('div', 'calc-inputs');
  for (const it of items) {
    const box = el('div', 'calc-input');
    box.appendChild(el('div', 'calc-input-label', it.label));
    box.appendChild(el('div', 'calc-input-value', String(it.value)));
    wrap.appendChild(box);
  }
  return wrap;
}

function makeCalcDerived(label, formula, value) {
  const box = el('div', 'calc-derived');
  box.appendChild(el('div', 'calc-derived-label', label));
  if (formula) box.appendChild(el('div', 'calc-derived-formula', formula));
  box.appendChild(el('div', 'calc-derived-value', value));
  return box;
}

// ── step 5: personality
function renderPersonalityStep(panel, step) {
  const wrap = el('div', 'personality-wrap');
  const card = el('div', 'character-card');
  const title = step.data.archetype_label
    ? `CPU CHARACTER SHEET — ${step.data.archetype_label.toUpperCase()}`
    : 'CPU CHARACTER SHEET';
  card.appendChild(el('div', 'character-card-title', title));
  const traits = el('div', 'character-traits');
  traits.appendChild(makeTraitRow('Risk appetite', step.data.risk_appetite));
  traits.appendChild(makeTraitRow('Attentiveness', step.data.attentiveness_score));
  traits.appendChild(makeTraitRow('Bluff frequency', step.data.bluff_frequency));
  card.appendChild(traits);
  wrap.appendChild(card);

  const derivedWrap = el('div', 'derived-wrap');
  derivedWrap.appendChild(makeStatBox('Spot-on EV bias', fmtNum(step.data.spot_on_ev_bias, 3)));
  derivedWrap.appendChild(makeStatBox('Challenge threshold', fmtNum(step.data.challenge_threshold, 3)));
  if (step.data.blind_aggression_active) {
    derivedWrap.appendChild(makeStatBox('Boost magnitude', '+' + fmtNum(step.data.boost_magnitude, 3)));
    derivedWrap.appendChild(makeStatBox('Effective challenge prob', fmtNum(step.data.effective_challenge_prob, 3)));
    derivedWrap.appendChild(makeStatBox('Lowered threshold', fmtNum(step.data.effective_challenge_threshold, 3)));
  }
  wrap.appendChild(derivedWrap);

  panel.appendChild(wrap);
}

// ── step 6: decision
function renderDecisionStep(panel, step) {
  $('step-narrative').textContent =
    'Three candidate actions are scored on the same scale — expected dice change. Challenge is gated by a confidence threshold; whichever EV is highest wins.';

  const d = step.data;
  const ctx = currentResult.steps.find(s => s.step_id === 'context')?.data || {};
  const wrap = el('div', 'decision-wrap');

  // What does EV mean? — compact primer
  const primer = el('div', 'ev-primer');
  primer.appendChild(el('div', 'ev-primer-title', 'What does EV mean?'));
  const body = el('div', 'ev-primer-body');
  body.appendChild(el('p', null,
    'EV = expected value of the action, measured in dice gained or lost on average if you replayed this exact situation many times. ' +
    'Positive = you walk away with more dice in the long run; negative = fewer; zero = break-even.'));
  const list = el('ul', 'ev-primer-list');
  list.appendChild(makePrimerItem(
    'CHALLENGE',
    '+1 die if the bid is a lie (bidder loses one), −1 die if it\'s true (you lose one). ' +
    'So EV = 2·P(lie) − 1. The break-even point is exactly 50%; below the gate the move is auto-rejected.'
  ));
  list.appendChild(makePrimerItem(
    'SPOT-ON',
    '+1 die from every other player if your guess is exact (a windfall), −1 if you miss. ' +
    'EV scales with the number of players at the table — the more opponents, the bigger the upside when you nail it.'
  ));
  list.appendChild(makePrimerItem(
    'BID',
    'Making a legal bid doesn\'t immediately win or lose dice — it just passes the turn. ' +
    'So its EV is 0 by definition: it\'s the baseline that challenge and spot-on must beat.'
  ));
  body.appendChild(list);
  primer.appendChild(body);
  wrap.appendChild(primer);

  const challengeGatePassed =
    d.branch !== 'fallback_zero' &&
    d.effective_challenge_prob >= d.effective_challenge_threshold;
  const isChallengeWin = d.branch === 'challenge_ev' || d.branch === 'fallback_zero';
  const isSpotOnWin = d.branch === 'spot_on_ev';
  const isBidWin = d.branch === 'raise' || d.branch === 'bid';

  // Three EV candidate cards
  const evRow = el('div', 'ev-row');
  const challengeFormula = `2 × ${fmtPct(d.effective_challenge_prob)} − 1 = ${fmtNum(2 * d.effective_challenge_prob - 1, 2)}`;
  const challengeSub = challengeGatePassed
    ? `Gate ✓  ${fmtPct(d.effective_challenge_prob)} ≥ ${fmtPct(d.effective_challenge_threshold)}\n${challengeFormula}`
    : `Gate ✗  ${fmtPct(d.effective_challenge_prob)} < ${fmtPct(d.effective_challenge_threshold)} — EV forced to 0`;
  evRow.appendChild(makeEVCard(
    'CHALLENGE',
    d.ev_challenge,
    challengeSub,
    challengeGatePassed,
    isChallengeWin,
  ));
  const spotOnSub = ctx.spot_on_prob !== undefined
    ? `P(exact) ${fmtPct(ctx.spot_on_prob)} × ${(ctx.num_active_players ?? 1) - 1} other player(s)\nminus the cost when wrong`
    : 'Expected dice from an exact-count call';
  evRow.appendChild(makeEVCard(
    'SPOT-ON',
    d.ev_spot_on,
    spotOnSub,
    true,
    isSpotOnWin,
  ));
  const bidSub = ctx.best_bid_desc && ctx.best_bid_desc !== 'none'
    ? `Best legal: ${ctx.best_bid_desc} @ ${fmtPct(ctx.best_bid_prob ?? 0)}\nbaseline — passes the turn`
    : 'No legal bid available';
  evRow.appendChild(makeEVCard(
    'BID',
    d.ev_bid_baseline,
    bidSub,
    true,
    isBidWin,
  ));
  wrap.appendChild(evRow);

  // Convergence arrow
  wrap.appendChild(el('div', 'flow-merge', '↓ argmax ↓'));

  // Final decision pill
  const pill = el('div', 'decision-pill');
  pill.appendChild(el('span', 'decision-action', d.action));
  if (d.bid_count !== null && d.bid_face !== null) {
    const bidLine = el('div', 'decision-bid-line');
    bidLine.appendChild(el('span', 'decision-bid-count', String(d.bid_count)));
    bidLine.appendChild(makeDieSVG(d.bid_face, 48));
    pill.appendChild(bidLine);
  }
  wrap.appendChild(pill);

  wrap.appendChild(el('div', 'decision-reason font-body', d.reason));
  wrap.appendChild(el('div', 'decision-branch-tag', `branch: ${d.branch}`));

  panel.appendChild(wrap);
}

function makePrimerItem(label, body) {
  const li = el('li', 'ev-primer-item');
  li.appendChild(el('span', 'ev-primer-tag', label));
  li.appendChild(el('span', 'ev-primer-text', body));
  return li;
}

// Bipolar EV color: red at -0.5, yellow at 0, green at +0.5 (clamped)
function evColor(value) {
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const t = (clamped + 0.5);
  return `hsl(${t * 120}, 70%, 55%)`;
}

function makeEVCard(action, ev, subInfo, active, isWinner) {
  const card = el('div', 'ev-card');
  if (isWinner) card.classList.add('ev-card-winner');
  if (!active) card.classList.add('ev-card-gated');

  card.appendChild(el('div', 'ev-card-action', action));

  const valWrap = el('div', 'ev-value-wrap');
  const valTxt = (ev > 0 ? '+' : '') + fmtNum(ev, 2);
  const val = el('div', 'ev-card-value', valTxt);
  const color = evColor(ev);
  val.style.color = color;
  val.style.textShadow = `0 0 14px ${color}`;
  valWrap.appendChild(val);
  valWrap.appendChild(el('div', 'ev-card-units', 'dice'));
  card.appendChild(valWrap);

  // Bipolar bar centred at 0
  const bar = el('div', 'ev-bar');
  bar.appendChild(el('div', 'ev-bar-zero'));
  const marker = el('div', 'ev-bar-marker');
  const clamped = Math.max(-0.5, Math.min(0.5, ev));
  marker.style.left = ((clamped + 0.5) * 100) + '%';
  marker.style.background = color;
  marker.style.boxShadow = `0 0 8px ${color}`;
  bar.appendChild(marker);
  card.appendChild(bar);

  const scaleRow = el('div', 'ev-bar-scale');
  scaleRow.appendChild(el('span', null, '−0.5'));
  scaleRow.appendChild(el('span', null, '0'));
  scaleRow.appendChild(el('span', null, '+0.5'));
  card.appendChild(scaleRow);

  card.appendChild(el('div', 'ev-card-sub font-body', subInfo));

  if (isWinner) card.appendChild(el('div', 'ev-card-winner-tag', '★ WINNER'));
  return card;
}

// ============================================================
// REUSABLE WIDGETS
// ============================================================
function makeStatBox(label, value) {
  const box = el('div', 'stat-box');
  box.appendChild(el('div', 'stat-box-label', label));
  box.appendChild(el('div', 'stat-box-value', value));
  return box;
}

function makeProbBar(label, value, caption) {
  const wrap = el('div', 'prob-bar-wrap');
  const head = el('div', 'prob-bar-head');
  head.appendChild(el('span', 'prob-bar-label', label));
  head.appendChild(el('span', 'prob-bar-value', fmtPct(value)));
  wrap.appendChild(head);

  const track = el('div', 'prob-bar-track');
  const fill = el('div', 'prob-bar-fill');
  const pct = Math.max(0, Math.min(1, value)) * 100;
  fill.style.width = pct + '%';
  track.appendChild(fill);
  wrap.appendChild(track);

  if (caption) wrap.appendChild(el('div', 'prob-bar-caption', caption));
  return wrap;
}

function makeScoreCard(label, value, caption) {
  const card = el('div', 'score-card');
  card.appendChild(el('div', 'score-card-label', label));
  card.appendChild(el('div', 'score-card-value', value));
  if (caption) card.appendChild(el('div', 'score-card-caption', caption));
  return card;
}

function makeTraitRow(label, value) {
  const row = el('div', 'trait-row');
  row.appendChild(el('div', 'trait-label', label));
  const pips = el('div', 'trait-pips');
  // 10 pips, each filled if value/10 > pip index
  const filled = Math.round(value / 10);
  for (let i = 0; i < 10; i++) {
    const pip = el('span', 'trait-pip');
    if (i < filled) pip.classList.add('trait-pip-filled');
    pips.appendChild(pip);
  }
  row.appendChild(pips);
  row.appendChild(el('div', 'trait-value', value + '/100'));
  return row;
}

// ============================================================
// NAVIGATION WIRING
// ============================================================
function setupNav() {
  $('btn-prev').addEventListener('click', () => {
    if (currentStepIdx > 0) {
      currentStepIdx -= 1;
      renderStep();
    }
  });
  $('btn-next').addEventListener('click', () => {
    if (currentStepIdx < currentResult.steps.length - 1) {
      currentStepIdx += 1;
      renderStep();
    }
  });
  $('btn-back-to-picker').addEventListener('click', backToPicker);
}

document.addEventListener('DOMContentLoaded', () => {
  setupNav();
  loadPicker();
});
