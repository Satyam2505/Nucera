// Pure, framework-free time/greeting logic — kept separate from the landing
// page's JSX so it can be unit tested without rendering anything and reused
// anywhere else a greeting might be needed later.

export type TimePeriod = "morning" | "afternoon" | "evening" | "night";

// Boundaries: 05:00-11:59 morning, 12:00-16:59 afternoon, 17:00-21:59
// evening, 22:00-04:59 night. Uses the browser's local time (Date's local
// getHours()) — never UTC, never a hardcoded timezone.
export function getTimePeriod(date: Date): TimePeriod {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 22) return "evening";
  return "night";
}

const PERIOD_LABEL: Record<TimePeriod, string> = {
  morning: "Good morning",
  afternoon: "Good afternoon",
  evening: "Good evening",
  night: "Still studying",
};

// Handles "aditya", "ADITYA KUMAR", "  aditya   kumar  " etc. — takes the
// first whitespace-separated token and normalizes it to Title Case. Returns
// null for anything empty/missing so callers can fall back cleanly.
export function getFirstName(name?: string | null): string | null {
  if (!name) return null;
  const first = name.trim().split(/\s+/)[0];
  if (!first) return null;
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}

// "Good evening, Aditya." / "Good evening." / "Still studying, Aditya?" /
// "Still studying?" — the only period that reads as a question is "night".
export function getGreeting(date: Date, firstName?: string | null): string {
  const period = getTimePeriod(date);
  const name = getFirstName(firstName);
  const base = PERIOD_LABEL[period];
  const punctuation = period === "night" ? "?" : ".";
  return name ? `${base}, ${name}${punctuation}` : `${base}${punctuation}`;
}
