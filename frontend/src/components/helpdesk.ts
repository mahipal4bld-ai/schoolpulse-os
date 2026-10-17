export type TicketStatus = "open" | "assigned" | "in_progress" | "waiting_on_parent" | "resolved" | "closed";
export type Ticket = {
  id: string; number: number; category: string; subject: string; body: string; priority: "normal" | "high" | "urgent"; status: TicketStatus;
  student_name: string; guardian_name?: string; assignee_name?: string | null; assignee_user_id?: string | null; overdue: boolean; created_at: string;
  last_activity_at: string; sla_due_at: string; unread_parent: number; unread_staff: number; rating: { score: number; comment: string } | null;
  can_reopen?: boolean; reopen_count: number; side?: "parent" | "manager" | "assignee";
  messages?: { id: string; body: string; internal: boolean; side: "parent" | "staff"; created_at: string; author_name: string; mine: boolean }[];
};

export const CATEGORY_LABEL: Record<string, string> = {
  fees: "Fees", transport: "Transport", academics: "Academics", documents: "Documents", uniform_books: "Uniform & books", technical: "App / login", other: "Other",
};

type Tone = "neutral" | "success" | "warning" | "brand" | "error";
export const STATUS_META: Record<TicketStatus, { label: string; parentLabel: string; tone: Tone }> = {
  open: { label: "New", parentLabel: "Received", tone: "warning" },
  assigned: { label: "Assigned", parentLabel: "Received", tone: "warning" },
  in_progress: { label: "In progress", parentLabel: "In progress", tone: "brand" },
  waiting_on_parent: { label: "Waiting on parent", parentLabel: "Needs your reply", tone: "warning" },
  resolved: { label: "Resolved", parentLabel: "Resolved", tone: "success" },
  closed: { label: "Closed", parentLabel: "Closed", tone: "neutral" },
};

/** Moves offered in the UI — the server enforces the same table. */
export const STAFF_MOVES: Partial<Record<TicketStatus, TicketStatus[]>> = {
  open: ["in_progress", "resolved"], assigned: ["in_progress", "resolved"], in_progress: ["waiting_on_parent", "resolved"],
  waiting_on_parent: ["in_progress", "resolved"], resolved: ["closed", "in_progress"],
};
export const MOVE_LABEL: Record<string, string> = { in_progress: "Start working", waiting_on_parent: "Ask parent", resolved: "Resolve", closed: "Close" };
