export const COLORS = { normal: "#2dd4bf", warning: "#f5a524", alarm: "#ff4d4f" };

const RANK = { normal: 0, warning: 1, alarm: 2 };

export const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

export const fmt = (value, decimals = 1) => (value == null || Number.isNaN(value) ? "--" : Number(value).toFixed(decimals));

export function highState(value, limits) {
  if (value == null || !limits || limits.warning == null) return "normal";
  if (value > limits.alarm) return "alarm";
  return value > limits.warning ? "warning" : "normal";
}

export function lowState(value, limits) {
  if (value == null || !limits || limits.low_warning == null) return "normal";
  if (value < limits.low_alarm) return "alarm";
  return value < limits.low_warning ? "warning" : "normal";
}

export function stateFor(value, limits) {
  return worst(highState(value, limits), lowState(value, limits));
}

export const worst = (...states) => states.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), "normal");
