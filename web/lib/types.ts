export type Status =
  | "new"
  | "reviewing"
  | "applied"
  | "oa"
  | "interview"
  | "offer"
  | "rejected"
  | "skipped";

export interface FitComponent {
  points: number;
  max: number;
  why: string;
  matched?: string[];
  missing?: string[];
}

export interface Notes {
  gaps?: string;
  actions?: string;
  standout?: string;
  keyword_coverage?: { present: string[]; missing: string[] };
}

export interface Posting {
  id: string;
  company: string;
  company_slug: string;
  title: string;
  apply_url: string;
  locations: string[];
  is_seattle_metro: boolean;
  is_remote_us: boolean;
  term: string;
  posted_at: string | null;
  first_seen_at: string | null;
  closes_at: string | null;
  closes_kind: string;
  closes_evidence: string | null;
  days_remaining: number | null;
  is_closed: boolean;
  fit: number;
  fit_breakdown: Record<string, FitComponent>;
  eligibility_flags: string[];
  status: Status;
  resume_pdf: string | null;
  resume_tex: string | null;
  resume_approved: boolean;
  prep_state: "ready" | "needs_improvement" | null;
  notes_preview: string;
  has_notes: boolean;
  // detail-only
  notes?: Notes;
  sources?: { type: string; url: string }[];
  description?: string;
  user_notes?: string;
}

export interface Snapshot {
  postings: Posting[];
  stats: {
    open: number;
    seattle: number;
    new_today: number;
    gaps_top: { keyword: string; seen_count: number; covered: boolean }[];
  };
}
