import type { Posting, Snapshot, Status } from "./types";

// Two modes (spec §14):
//  - live:   `radar serve` is running; /api/* is proxied to it (writable).
//  - static: no backend; fall back to /data.json exported by `radar export`.
// We probe the live API once and cache the result for the session.

let liveMode: boolean | null = null;

async function isLive(): Promise<boolean> {
  if (liveMode !== null) return liveMode;
  try {
    const r = await fetch("/api/snapshot", { cache: "no-store" });
    liveMode = r.ok;
  } catch {
    liveMode = false;
  }
  return liveMode;
}

export async function getSnapshot(seattleOnly = false): Promise<Snapshot> {
  if (await isLive()) {
    const r = await fetch(`/api/snapshot${seattleOnly ? "?seattle=1" : ""}`, {
      cache: "no-store",
    });
    if (r.ok) return r.json();
  }
  // static fallback
  const r = await fetch("/data.json", { cache: "no-store" });
  const snap: Snapshot = await r.json();
  if (seattleOnly) {
    snap.postings = snap.postings.filter((p) => p.is_seattle_metro);
  }
  return snap;
}

export async function getPosting(id: string): Promise<Posting | null> {
  if (await isLive()) {
    const r = await fetch(`/api/postings/${id}`, { cache: "no-store" });
    if (r.ok) return r.json();
  }
  // static: the snapshot rows lack detail fields; return what we have.
  const snap = await getSnapshot();
  return snap.postings.find((p) => p.id === id) ?? null;
}

export async function setStatus(id: string, status: Status): Promise<boolean> {
  if (!(await isLive())) return false;
  const r = await fetch(`/api/postings/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return r.ok;
}

export async function generate(id: string): Promise<Posting | null> {
  if (!(await isLive())) return null;
  const r = await fetch(`/api/postings/${id}/generate`, { method: "POST" });
  if (!r.ok) return null;
  return getPosting(id);
}

export async function approveResume(id: string, approved: boolean): Promise<boolean> {
  if (!(await isLive())) return false;
  const r = await fetch(`/api/postings/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  return r.ok;
}

export async function saveUserNotes(id: string, text: string): Promise<boolean> {
  if (!(await isLive())) return false;
  const r = await fetch(`/api/postings/${id}/user_notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.ok;
}

export async function addManual(payload: {
  url: string;
  company?: string;
  title?: string;
}): Promise<boolean> {
  if (!(await isLive())) return false;
  const r = await fetch(`/api/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.ok;
}
