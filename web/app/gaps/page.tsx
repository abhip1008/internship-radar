"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSnapshot } from "@/lib/api";
import ThemeToggle from "../ThemeToggle";

interface Gap {
  keyword: string;
  seen_count: number;
}

export default function GapsPage() {
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    getSnapshot().then((snap) => {
      setGaps(snap.stats.gaps_top);
      setTotal(snap.stats.open);
    });
  }, []);

  const max = gaps.reduce((m, g) => Math.max(m, g.seen_count), 1);

  return (
    <div className="container">
      <div className="topbar">
        <h1>Gap rollup</h1>
        <div className="stats">
          <Link href="/">← back to table</Link>
          <ThemeToggle />
        </div>
      </div>
      <div style={{ padding: "20px" }}>
        <p className="muted" style={{ maxWidth: 640 }}>
          Skills required across your open postings, ranked by frequency. This tells you what to
          build next better than any single posting does (spec §11).
        </p>
        {gaps.length === 0 ? (
          <div className="empty">
            No gap data yet. Run <code>radar notes &lt;id&gt;</code> across postings, or generate
            resumes to populate coverage.
          </div>
        ) : (
          <div style={{ marginTop: 20 }}>
            {gaps.map((g) => (
              <div
                key={g.keyword}
                style={{ display: "flex", alignItems: "center", gap: 12, margin: "6px 0" }}
              >
                <div style={{ width: 140, textAlign: "right", fontWeight: 500 }}>{g.keyword}</div>
                <div
                  style={{
                    height: 18,
                    width: `${(g.seen_count / max) * 60}%`,
                    minWidth: 20,
                    background: "var(--urgent-1)",
                    borderRadius: "var(--radius)",
                  }}
                />
                <div className="muted">
                  {g.seen_count} of {total}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
