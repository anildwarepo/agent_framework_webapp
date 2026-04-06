// Deterministic color per label (same label -> same color), good contrast on dark bg.
function hashString(str: string): number {
  // FNV-1a 32-bit
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function colorForLabel(label: string): string {
  const hue = hashString(label) % 360;
  // HSL works fine in react-force-graph; tune S/L for dark background (#0B1220)
  return `hsl(${hue}, 70%, 55%)`;
}
