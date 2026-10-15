// Indian locale formatting. Server stores UTC; display in Asia/Kolkata.
const TZ = "Asia/Kolkata";

export function formatINR(amount: number) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = value.length === 10 ? new Date(`${value}T00:00:00+05:30`) : new Date(value);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: TZ });
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: TZ,
  });
}

export function todayLabel() {
  return new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: TZ });
}

export function greetingKey(): "goodMorning" | "goodAfternoon" | "goodEvening" {
  const h = Number(new Date().toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: TZ }));
  return h < 12 ? "goodMorning" : h < 17 ? "goodAfternoon" : "goodEvening";
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

export const ROLE_LABEL: Record<string, string> = {
  owner: "School Owner",
  principal: "Principal",
  school_admin: "School Administrator",
  accountant: "Accountant",
  admission_coordinator: "Admission Coordinator",
  teacher: "Teacher",
  transport_coordinator: "Transport Coordinator",
  parent: "Parent",
};
