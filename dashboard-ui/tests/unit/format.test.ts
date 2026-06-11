import { pct, pctPlusMinus, numPlusMinus, ciText, edgeChip, formatDate } from '../../src/lib/format';

test('pct formats a probability', () => {
  expect(pct(0.147)).toBe('15%');
  expect(pct(0.288, 1)).toBe('28.8%');
  expect(pct(null)).toBe('—');
});

test('pctPlusMinus binds the estimate to its SE (never naked)', () => {
  expect(pctPlusMinus(0.288, 0.0032)).toBe('29% ±0.3');   // value% ±(se in points)
  expect(pctPlusMinus(0.10, 0.0)).toBe('10% ±0');
  expect(pctPlusMinus(null, 0.01)).toBe('—');
  expect(pctPlusMinus(0.10, null)).toBe('10% ±?');         // value present but no SE -> explicit unknown, never silent
});

test('ciText renders a 94% HDI', () => {
  expect(ciText([-0.698, 1.151])).toBe('[−0.70, 1.15] (94% HDI)');
});

test('edgeChip shows a signed edge', () => {
  expect(edgeChip(0.0686)).toBe('▲ +6.9%');
  expect(edgeChip(-0.02)).toBe('▼ −2.0%');
  expect(edgeChip(0)).toBe('no edge');
});

test('formatDate strips a trailing time', () => {
  expect(formatDate('2023-01-28 00:00:00')).toBe('2023-01-28');
  expect(formatDate('2024-05-01')).toBe('2024-05-01');
});

// --- extra edge cases (the no-naked invariant + sign/rounding) ---

test('pctPlusMinus: tiny SE rounds to 1dp, larger SE to 0dp', () => {
  expect(pctPlusMinus(0.5, 0.004)).toBe('50% ±0.4');   // 0.4 pts -> 1dp
  expect(pctPlusMinus(0.5, 0.05)).toBe('50% ±5');      // 5 pts   -> 0dp
});

test('pctPlusMinus: NaN value or NaN SE never leaks a naked number', () => {
  expect(pctPlusMinus(NaN, 0.01)).toBe('—');
  expect(pctPlusMinus(0.10, NaN)).toBe('10% ±?');
});

test('edgeChip: a very small negative edge still renders signed with the U+2212 minus', () => {
  expect(edgeChip(-0.001)).toBe('▼ −0.1%');
  expect(edgeChip(null)).toBe('no edge');
  expect(edgeChip(NaN)).toBe('no edge');
});

test('pct: very small probability does not round to a misleading naked 0 without %', () => {
  expect(pct(0.004)).toBe('0%');     // still carries the % unit
  expect(pct(0.004, 1)).toBe('0.4%');
});

// --- numPlusMinus (E[Pts] / E[GD]: a NON-probability estimate that still carries its SE) ---

test('numPlusMinus binds a plain-number estimate to its SE (never naked)', () => {
  expect(numPlusMinus(6.4, 0.02)).toBe('6.4 ±0.0');          // E[Pts]: unsigned, 1dp
  expect(numPlusMinus(4.1, 0.03, { signedValue: true })).toBe('+4.1 ±0.0');   // E[GD]: signed +
  expect(numPlusMinus(-5.3, 0.04, { signedValue: true })).toBe('−5.3 ±0.0');  // E[GD]: U+2212 minus
});

test('numPlusMinus: null value -> em-dash, null/NaN SE -> explicit ±? (never silent)', () => {
  expect(numPlusMinus(null, 0.1)).toBe('—');
  expect(numPlusMinus(undefined, 0.1)).toBe('—');
  expect(numPlusMinus(NaN, 0.1)).toBe('—');
  expect(numPlusMinus(5.0, null)).toBe('5.0 ±?');
  expect(numPlusMinus(5.0, NaN)).toBe('5.0 ±?');
  expect(numPlusMinus(Infinity, 0.1)).toBe('—');
});

test('numPlusMinus respects the dp option', () => {
  expect(numPlusMinus(5.25, 0.123, { dp: 2 })).toBe('5.25 ±0.12');
  expect(numPlusMinus(5.25, 0.123, { dp: 0 })).toBe('5 ±0');
});

test('non-finite inputs never render a malformed token', () => {
  expect(pct(Infinity)).toBe('—');
  expect(pct(-Infinity)).toBe('—');
  expect(pctPlusMinus(Infinity, 0.01)).toBe('—');
  expect(pctPlusMinus(0.10, Infinity)).toBe('10% ±?');
  expect(edgeChip(Infinity)).toBe('no edge');
  expect(edgeChip(-Infinity)).toBe('no edge');
});
