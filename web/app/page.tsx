"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Posting, Snapshot, Status } from "@/lib/types";
import { getSnapshot, setStatus, autoApply } from "@/lib/api";
import { relTime, runway } from "@/lib/format";
import Drawer from "./Drawer";
import ThemeToggle from "./ThemeToggle";

type TabKey = "all" | "seattle" | "new" | "closing" | "ready" | "applied";

export default function Home() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<TabKey>("seattle");
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [showClosed, setShowClosed] = useState(false);
  const [prepping, setPrepping] = useState(false);
  const [prepMsg, setPrepMsg] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const data = await getSnapshot();
    setSnap(data);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => {
    if (!snap) return [];
    let list = snap.postings.slice();
    if (!showClosed) list = list.filter((p) => !p.is_closed);
    if (tab === "seattle") list = list.filter((p) => p.is_seattle_metro);
    if (tab === "new") list = list.filter((p) => p.status === "new" && isToday(p.first_seen_at));
    if (tab === "closing")
      list = list.filter(
        (p) => p.closes_kind === "rolling" || (p.days_remaining !== null && p.days_remaining <= 7)
      );
    if (tab === "ready") list = list.filter((p) => p.resume_approved);
    if (tab === "applied") list = list.filter((p) => p.status === "applied");
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (p) =>
          p.company.toLowerCase().includes(needle) ||
          p.title.toLowerCase().includes(needle) ||
          p.locations.join(" ").toLowerCase().includes(needle) ||
          p.notes_preview.toLowerCase().includes(needle)
      );
    }
    return list;
  }, [snap, tab, q, showClosed]);

  const counts = useMemo(() => {
    const all = snap?.postings.filter((p) => !p.is_closed) ?? [];
    return {
      all: all.length,
      seattle: all.filter((p) => p.is_seattle_metro).length,
      new: all.filter((p) => p.status === "new" && isToday(p.first_seen_at)).length,
      closing: all.filter(
        (p) => p.closes_kind === "rolling" || (p.days_remaining !== null && p.days_remaining <= 7)
      ).length,
      ready: all.filter((p) => p.resume_approved).length,
      applied: all.filter((p) => p.status === "applied").length,
    };
  }, [snap]);

  const runAutoApply = async () => {
    setPrepping(true);
    setPrepMsg(null);
    const res = await autoApply();
    if (!res) {
      setPrepMsg("Auto-prepare needs the live API (run `make serve`).");
    } else {
      setPrepMsg(
        `Tailored ${res.tailored} for review · ${res.thin_jd} thin-JD (review carefully) · held ${res.needs_improvement} with skill gaps — of ${res.considered}. Nothing is Ready until you Approve it.`
      );
      await load();
    }
    setPrepping(false);
  };

  // Keyboard nav (§13): j/k move, Enter opens, a=applied, x=skip, / focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (openId) {
        if (e.key === "Escape") setOpenId(null);
        return;
      }
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") {
        if (e.key === "Escape") (target as HTMLInputElement).blur();
        return;
      }
      if (e.key === "j") setCursor((c) => Math.min(c + 1, rows.length - 1));
      else if (e.key === "k") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "Enter" && rows[cursor]) setOpenId(rows[cursor].id);
      else if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "a" && rows[cursor]) quickStatus(rows[cursor], "applied");
      else if (e.key === "x" && rows[cursor]) quickStatus(rows[cursor], "skipped");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, cursor, openId]);

  const quickStatus = async (p: Posting, s: Status) => {
    applyStatus(p.id, s);
    await setStatus(p.id, s);
  };

  const applyStatus = (id: string, s: Status) => {
    setSnap((prev) =>
      prev
        ? { ...prev, postings: prev.postings.map((p) => (p.id === id ? { ...p, status: s } : p)) }
        : prev
    );
  };

  const applyApprove = (id: string, approved: boolean) => {
    setSnap((prev) =>
      prev
        ? {
            ...prev,
            postings: prev.postings.map((p) =>
              p.id === id ? { ...p, resume_approved: approved } : p
            ),
          }
        : prev
    );
  };

  if (!snap) return <div className="empty">Loading Internship Radar…</div>;

  return (
    <div className="container">
      <div className="topbar">
        <h1>Internship Radar</h1>
        <div className="stats">
          {snap.stats.open} open · {snap.stats.new_today} new today ·{" "}
          <Link href="/gaps">gaps ↗</Link>
          <ThemeToggle />
        </div>
      </div>

      <div className="controls">
        <input
          ref={searchRef}
          className="search"
          placeholder="filter by company, role, or skill  ( / )"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="tabs">
          <Tab k="all" tab={tab} setTab={setTab} label="All" count={counts.all} />
          <Tab k="seattle" tab={tab} setTab={setTab} label="Seattle" count={counts.seattle} />
          <Tab k="new" tab={tab} setTab={setTab} label="New" count={counts.new} />
          <Tab
            k="closing"
            tab={tab}
            setTab={setTab}
            label="Closing soon"
            count={counts.closing}
          />
          <Tab k="ready" tab={tab} setTab={setTab} label="Ready" count={counts.ready} />
          <Tab k="applied" tab={tab} setTab={setTab} label="Applied" count={counts.applied} />
          <span className="spacer" />
          <button className="tab" onClick={runAutoApply} disabled={prepping} title="Auto-tailor resumes for clean-match Seattle postings; hold ones with skill gaps">
            {prepping ? "Preparing…" : "⚡ Auto-prepare"}
          </button>
          <button className="tab" onClick={() => setShowClosed((v) => !v)}>
            {showClosed ? "Hide closed" : "Show closed"}
          </button>
          <button className="tab" onClick={load}>
            ↻ Refresh
          </button>
        </div>
        {prepMsg && (
          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            {prepMsg}
          </div>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="empty">
          {tab === "seattle"
            ? `No open Seattle postings match these filters. ${counts.all - counts.seattle} are outside the metro.`
            : "No postings match these filters."}
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: "36%" }}>ROLE</th>
              <th style={{ width: "16%" }}>LOCATION</th>
              <th style={{ width: "8%" }}>POSTED</th>
              <th style={{ width: "16%" }}>CLOSES</th>
              <th style={{ width: "12%" }}>RESUME</th>
              <th className="right" style={{ width: "6%" }}>
                FIT
              </th>
              <th style={{ width: "6%" }}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <Row
                key={p.id}
                p={p}
                selected={i === cursor}
                onClick={() => {
                  setCursor(i);
                  setOpenId(p.id);
                }}
              />
            ))}
          </tbody>
        </table>
      )}

      <div className="kbd">
        j/k move · Enter open · a applied · x skip · / search
      </div>

      {openId && (
        <Drawer
          id={openId}
          onClose={() => setOpenId(null)}
          onStatusChange={applyStatus}
          onApprove={applyApprove}
        />
      )}
    </div>
  );
}

function Tab({
  k,
  tab,
  setTab,
  label,
  count,
}: {
  k: TabKey;
  tab: TabKey;
  setTab: (t: TabKey) => void;
  label: string;
  count: number;
}) {
  return (
    <button className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
      {label}
      <span className="count">{count}</span>
    </button>
  );
}

function Row({
  p,
  selected,
  onClick,
}: {
  p: Posting;
  selected: boolean;
  onClick: () => void;
}) {
  const rw = runway(p);
  return (
    <tr className={`${selected ? "selected" : ""} ${p.is_closed ? "closed" : ""}`} onClick={onClick}>
      <td>
        <div className="role-company">
          <span className={`dot ${p.is_seattle_metro ? "metro" : "other"}`} />
          {p.company}
        </div>
        <div className="role-title">{p.title}</div>
      </td>
      <td className="muted">{p.locations[0] ?? "—"}</td>
      <td className="muted">{relTime(p.first_seen_at)}</td>
      <td>
        <div className="runway">
          <div className="runway-track">
            <div
              className="runway-fill"
              style={{ width: `${rw.fillPct}%`, background: rw.color }}
            />
          </div>
          <div className="runway-label">
            {rw.label} {rw.sub && <span>· {rw.sub}</span>}
          </div>
        </div>
      </td>
      <td className="resume-links" onClick={(e) => e.stopPropagation()}>
        {p.resume_approved ? (
          <span className="prep ready" title="You approved this — ready to submit">
            ✓ Ready
          </span>
        ) : p.prep_state === "tailored" ? (
          <span className="prep review" title="Tailored — open to review the diff and approve">
            ⏳ Review
          </span>
        ) : p.prep_state === "thin_jd" ? (
          <span className="prep thin" title="Too little job-description text to assess — open to read the full JD">
            ◍ Thin JD
          </span>
        ) : p.prep_state === "needs_improvement" ? (
          <span className="prep gaps" title="Held — missing must-have skills for this role">
            ⚠ Gaps
          </span>
        ) : p.resume_tex ? (
          <>
            {p.resume_pdf && <span>PDF</span>}
            <span className="muted">TEX</span>
          </>
        ) : (
          <span className="muted">Generate</span>
        )}
      </td>
      <td className="right fit">{p.fit}</td>
      <td>
        <span className={`pill ${p.status}`}>{p.status}</span>
      </td>
    </tr>
  );
}

function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const n = new Date();
  return d.toDateString() === n.toDateString();
}
