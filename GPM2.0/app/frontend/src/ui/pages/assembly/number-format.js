// Repeated tooltip formatting is on the dense Local View render path. Reuse
// one locale formatter instead of constructing/consulting Intl per band.
const EN_US_INTEGER = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatIntegerEnUs(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? EN_US_INTEGER.format(numeric) : "0";
}

export function formatBpIntervalEnUs(start, end) {
  return `${formatIntegerEnUs(start)}-${formatIntegerEnUs(end)} bp`;
}
