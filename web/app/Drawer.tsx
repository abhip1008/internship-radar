"use client";

import { useEffect, useState } from "react";
import type { Posting, Status } from "@/lib/types";
import { getPosting, generate, setStatus, approveResume, saveUserNotes } from "@/lib/api";

const STATUSES: Status[] = [
  "new",
  "reviewing",
  "applied",
  "oa",
  "interview",
  "offer",
  "rejected",
  "skipped",
];

export default function Drawer({
  id,
  onClose,
  onStatusChange,
  onApprove,
}: {
  id: string;
  onClose: () => void;
  onStatusChange: (id: string, status: Status) => void;
  onApprove: (id: string, approved: boolean) => void;
}) {
  const [p, setP] = useState<Posting | null>(null);
  const [busy, setBusy] = useState(false);
  const [showJd, setShowJd] = useState(false);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let alive = true;
    getPosting(id).then((data) => {
      if (alive) {
        setP(data);
        setNotes(data?.user_notes ?? "");
      }
    });
    return () => {
      alive = false;
    };
  }, [id]);

  if (!p) {
    return (
      <>
        <div className="scrim" onClick={onClose} />
        <div className="drawer">Loading…</div>
      </>
    );
  }

  const doGenerate = async () => {
    setBusy(true);
    const updated = await generate(id);
    if (updated) setP(updated);
    setBusy(false);
  };

  const doStatus = async (s: Status) => {
    setP({ ...p, status: s });
    onStatusChange(id, s);
    await setStatus(id, s);
  };

  const fit = p.fit_breakdown || {};
  const assessment = p.prep_meta?.assessment;
  const diff = p.prep_meta?.diff ?? [];
  const changedCount = p.prep_meta?.changed_count ?? diff.filter((d) => d.changed).length;
  const assessLabel =
    assessment?.state === "strong"
      ? "Strong match"
      : assessment?.state === "needs_improvement"
        ? "Needs improvement"
        : assessment?.state === "thin_jd"
          ? "Limited info"
          : "";
  const assessColor =
    assessment?.state === "strong"
      ? "var(--ok)"
      : assessment?.state === "needs_improvement"
        ? "var(--urgent-1)"
        : "var(--ink-muted)";

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="drawer" role="dialog" aria-label={`${p.company} ${p.title}`}>
        <h2>{p.title}</h2>
        <div className="sub">
          {p.company} · {p.locations.join(", ") || "Location TBD"} · Fit {p.fit}
        </div>
        {p.eligibility_flags.map((f) => (
          <span className="badge" key={f}>
            {f}
          </span>
        ))}
        <div style={{ margin: "12px 0" }}>
          <a className="btn primary" href={p.apply_url} target="_blank" rel="noreferrer">
            Open application →
          </a>
        </div>

        {/* Notes — the three blocks, plain prose (§13) */}
        <section>
          <h3>Notes</h3>
          {p.notes && (p.notes.gaps || p.notes.actions || p.notes.standout) ? (
            <>
              {p.notes.gaps && (
                <div className="note-block">
                  <b>Gaps</b>
                  {p.notes.gaps}
                </div>
              )}
              {p.notes.actions && (
                <div className="note-block">
                  <b>Do this</b>
                  {p.notes.actions}
                </div>
              )}
              {p.notes.standout && (
                <div className="note-block">
                  <b>Standout signal</b>
                  {p.notes.standout}
                </div>
              )}
            </>
          ) : (
            <span className="muted">No notes yet. Generate to produce them.</span>
          )}
        </section>

        {/* Assessment — the honest read on this specific posting */}
        {assessment && (
          <section>
            <h3>Readiness</h3>
            <div className="note-block" style={{ color: assessColor }}>
              <b>{assessLabel}</b>
              {assessment.note}
            </div>
            {assessment.missing_must?.length > 0 && (
              <div>
                Missing must-haves:{" "}
                {assessment.missing_must.map((k) => (
                  <span className="kw miss" key={k}>
                    {k}
                  </span>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Resume */}
        <section>
          <h3>Resume</h3>
          {p.resume_approved && (
            <div className="note-block" style={{ color: "var(--ok)" }}>
              ✓ Approved by you — Ready to submit.
            </div>
          )}
          {p.resume_tex ? (
            <div className="resume-links">
              {p.resume_pdf && (
                <a href={fileUrl(p.resume_pdf)} target="_blank" rel="noreferrer">
                  Download .pdf
                </a>
              )}
              <a href={fileUrl(p.resume_tex)} target="_blank" rel="noreferrer">
                Download .tex
              </a>
              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button className="btn" onClick={doGenerate} disabled={busy}>
                  {busy ? "Working…" : "Regenerate"}
                </button>
                <button
                  className={`btn ${p.resume_approved ? "" : "primary"}`}
                  onClick={() => {
                    const next = !p.resume_approved;
                    setP({ ...p, resume_approved: next });
                    approveResume(id, next);
                    onApprove(id, next);
                  }}
                >
                  {p.resume_approved ? "✓ Approved — click to unapprove" : "Approve → mark Ready"}
                </button>
              </div>
            </div>
          ) : (
            <button className="btn primary" onClick={doGenerate} disabled={busy}>
              {busy ? "Generating…" : "Generate tailored resume"}
            </button>
          )}
        </section>

        {/* Diff vs. base — what was re-angled for THIS posting */}
        {diff.length > 0 && (
          <section>
            <h3>
              What changed for this role{" "}
              <span className="muted" style={{ textTransform: "none", fontWeight: 400 }}>
                ({changedCount} of {diff.length} bullets re-angled)
              </span>
            </h3>
            {changedCount === 0 && (
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                Selection and ordering were tailored to this JD, but bullet wording is verbatim —
                set <code>GEMINI_API_KEY</code> (free tier) to enable sentence-level re-angling.
              </div>
            )}
            {diff.map((d) => (
              <div key={d.id} className="note-block">
                <span className="muted" style={{ fontSize: 11 }}>
                  {d.source} {d.changed ? "· re-angled" : "· verbatim"}
                </span>
                {d.changed ? (
                  <>
                    <div style={{ color: "var(--ink-muted)", textDecoration: "line-through" }}>
                      {d.base}
                    </div>
                    <div style={{ color: "var(--ink)" }}>{d.final}</div>
                  </>
                ) : (
                  <div>{d.final}</div>
                )}
              </div>
            ))}
          </section>
        )}

        {/* Keyword coverage */}
        {p.notes?.keyword_coverage && (
          <section>
            <h3>Keyword coverage</h3>
            <div style={{ marginBottom: 6 }}>
              {p.notes.keyword_coverage.present.length ? (
                p.notes.keyword_coverage.present.map((k) => (
                  <span className="kw have" key={k}>
                    {k}
                  </span>
                ))
              ) : (
                <span className="muted">none</span>
              )}
            </div>
            <div>
              {p.notes.keyword_coverage.missing.length ? (
                p.notes.keyword_coverage.missing.map((k) => (
                  <span className="kw miss" key={k}>
                    {k}
                  </span>
                ))
              ) : (
                <span className="muted">no gaps</span>
              )}
            </div>
          </section>
        )}

        {/* Fit breakdown */}
        <section>
          <h3>Fit breakdown</h3>
          {Object.entries(fit).map(([k, c]) => (
            <div className="fitrow" key={k}>
              <span style={{ width: 110 }}>{k.replace("_", " ")}</span>
              <span className="bar">
                <span style={{ width: `${(c.points / (c.max || 1)) * 100}%` }} />
              </span>
              <span className="muted" style={{ width: 46, textAlign: "right" }}>
                {c.points}/{c.max}
              </span>
            </div>
          ))}
        </section>

        {/* Full JD, collapsed by default */}
        <section>
          <h3
            style={{ cursor: "pointer" }}
            onClick={() => setShowJd((v) => !v)}
          >
            Job description {showJd ? "▾" : "▸"}
          </h3>
          {showJd && <div className="jd">{p.description || "No description captured."}</div>}
        </section>

        {/* Your notes + status */}
        <section>
          <h3>Your notes</h3>
          <textarea
            className="usernotes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() => saveUserNotes(id, notes)}
            placeholder="Referrals, contacts, reminders…"
          />
          <div style={{ marginTop: 10 }}>
            <label className="muted" style={{ marginRight: 8 }}>
              Status
            </label>
            <select
              className="status"
              value={p.status}
              onChange={(e) => doStatus(e.target.value as Status)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </section>
      </div>
    </>
  );
}

// Resume files live under files/resumes on the backend; the API serves absolute
// paths. In live mode we can't stream them through the JSON API, so we surface
// the path. When hosted, symlink files/ into web/public to serve them directly.
function fileUrl(path: string): string {
  const name = path.split("/").pop();
  return `/resumes/${name}`;
}
