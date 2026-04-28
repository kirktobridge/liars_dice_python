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
  const wrap = el('div', 'context-wrap');
  wrap.appendChild(makeProbBar('Challenge probability', step.data.challenge_prob,
    'Chance the previous bid is a lie.'));
  wrap.appendChild(makeProbBar('Spot-on probability', step.data.spot_on_prob,
    `Chance the bid is exactly correct. With ${step.data.num_active_players} players, that translates to a spot-on EV of ${fmtNum(step.data.spot_on_ev, 2)} dice.`));
  wrap.appendChild(makeProbBar('Best legal bid probability', step.data.best_bid_prob,
    `CPU's strongest legal bid: ${step.data.best_bid_desc}.`));
  wrap.appendChild(makeProbBar('Effective challenge threshold', step.data.effective_threshold,
    'Floor at break-even (0.50). Higher means the CPU demands more confidence.'));

  const scoreRow = el('div', 'score-row');
  scoreRow.appendChild(makeScoreCard('Blind aggression score',
    fmtNum(step.data.blind_aggression_score),
    `Above ${step.data.blind_aggression_threshold} suggests the bidder is over-claiming.`));
  scoreRow.appendChild(makeScoreCard('Pressure-opportunity score',
    fmtNum(step.data.pressure_opportunity_score),
    'Above 0.45 (with cunning) tilts bid selection toward escalation.'));
  wrap.appendChild(scoreRow);

  panel.appendChild(wrap);
}

// ── step 5: personality
function renderPersonalityStep(panel, step) {
  const wrap = el('div', 'personality-wrap');
  const card = el('div', 'character-card');
  card.appendChild(el('div', 'character-card-title', 'CPU CHARACTER SHEET'));
  const traits = el('div', 'character-traits');
  traits.appendChild(makeTraitRow('Risk appetite', step.data.risk_appetite));
  traits.appendChild(makeTraitRow('Peer pressure', step.data.peer_pressure_score));
  traits.appendChild(makeTraitRow('Attentiveness', step.data.attentiveness_score));
  traits.appendChild(makeTraitRow('Positional cunning', step.data.positional_cunning));
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
  const wrap = el('div', 'decision-wrap');
  const pill = el('div', 'decision-pill');
  pill.appendChild(el('span', 'decision-action', step.data.action));
  if (step.data.bid_count !== null && step.data.bid_face !== null) {
    const bidLine = el('div', 'decision-bid-line');
    bidLine.appendChild(el('span', 'decision-bid-count', String(step.data.bid_count)));
    bidLine.appendChild(makeDieSVG(step.data.bid_face, 48));
    pill.appendChild(bidLine);
  }
  wrap.appendChild(pill);

  const reason = el('div', 'decision-reason font-body', step.data.reason);
  wrap.appendChild(reason);

  const meta = el('div', 'decision-meta');
  meta.appendChild(makeStatBox('Challenge EV', fmtNum(step.data.ev_challenge, 2) + ' dice'));
  meta.appendChild(makeStatBox('Spot-on EV', fmtNum(step.data.ev_spot_on, 2) + ' dice'));
  meta.appendChild(makeStatBox('Bid baseline', fmtNum(step.data.ev_bid_baseline, 2) + ' dice'));
  meta.appendChild(makeStatBox('Decision branch', step.data.branch));
  wrap.appendChild(meta);

  panel.appendChild(wrap);
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
