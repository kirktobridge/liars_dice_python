'use strict';

// Pip coordinates (cx%, cy%) within a 100×100 viewBox
const PIP_POSITIONS = {
  1: [[50, 50]],
  2: [[30, 30], [70, 70]],
  3: [[30, 30], [50, 50], [70, 70]],
  4: [[30, 30], [70, 30], [30, 70], [70, 70]],
  5: [[30, 30], [70, 30], [50, 50], [30, 70], [70, 70]],
  6: [[30, 25], [70, 25], [30, 50], [70, 50], [30, 75], [70, 75]],
};

function makeDieSVG(face, size) {
  const pips = PIP_POSITIONS[face] || PIP_POSITIONS[1];
  const ns = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.classList.add('die-face');

  const rect = document.createElementNS(ns, 'rect');
  rect.setAttribute('x', '4'); rect.setAttribute('y', '4');
  rect.setAttribute('width', '92'); rect.setAttribute('height', '92');
  rect.setAttribute('rx', '16'); rect.setAttribute('ry', '16');
  rect.setAttribute('fill', '#f4e5c2');
  rect.setAttribute('stroke', '#c8a84a');
  rect.setAttribute('stroke-width', '3');
  svg.appendChild(rect);

  const inner = document.createElementNS(ns, 'rect');
  inner.setAttribute('x', '8'); inner.setAttribute('y', '8');
  inner.setAttribute('width', '84'); inner.setAttribute('height', '84');
  inner.setAttribute('rx', '13'); inner.setAttribute('ry', '13');
  inner.setAttribute('fill', 'none');
  inner.setAttribute('stroke', 'rgba(255,255,255,0.25)');
  inner.setAttribute('stroke-width', '1.5');
  svg.appendChild(inner);

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
