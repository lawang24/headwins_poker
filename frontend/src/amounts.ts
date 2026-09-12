/** Wire amounts stay integral; cents mode uses 100 units per displayed chip. */
export function formatAmount(value: number, cents: boolean) {
  return (value / (cents ? 100 : 1)).toLocaleString(undefined, {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  });
}

export function inputAmount(value: number, cents: boolean) {
  return String(value / (cents ? 100 : 1));
}

export function parseAmount(value: string, cents: boolean) {
  if (!value.trim() || !/^\d+(\.\d{1,2})?$/.test(value)) return NaN;
  const scaled = Number(value) * (cents ? 100 : 1);
  return Math.abs(scaled - Math.round(scaled)) < 1e-7 ? Math.round(scaled) : NaN;
}
