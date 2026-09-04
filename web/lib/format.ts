import type { Posting } from "./types";

export function relTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

export function shortDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Runway bar model (spec §13): fill fraction + urgency color.
export interface Runway {
  fillPct: number;
  color: string;
  label: string;
  sub: string;
}

const U0 = "var(--urgent-0)";
const U1 = "var(--urgent-1)";
const U2 = "var(--urgent-2)";

export function runway(p: Posting): Runway {
  if (p.closes_kind === "rolling") {
    // Rolling means earlier is strictly better — pin the bar high and warm.
    return { fillPct: 100, color: U2, label: "Rolling", sub: "apply now" };
  }
  if (p.closes_kind === "unknown" || p.closes_at === null) {
    return { fillPct: 0, color: U0, label: "Unknown", sub: "" };
  }
  const days = p.days_remaining ?? 21;
  // Fill grows as the deadline approaches (30-day horizon).
  const fillPct = Math.max(4, Math.min(100, ((30 - days) / 30) * 100));
  let color = U0;
  if (days <= 7) color = U2;
  else if (days <= 21) color = U1;
  const prefix = p.closes_kind === "estimated" ? "~" : "";
  const label = prefix + shortDate(p.closes_at);
  const sub =
    p.closes_kind === "estimated" ? "est." : days >= 0 ? `${days} days` : "closed";
  return { fillPct, color, label, sub };
}

export function fitColor(fit: number): string {
  return fit >= 60 ? "var(--ink)" : "var(--ink-muted)";
}
