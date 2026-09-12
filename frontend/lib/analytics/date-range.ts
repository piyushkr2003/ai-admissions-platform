import type { AnalyticsDateRangePreset } from "@/types/analytics";

/** Mirrors backend/app/analytics/dates.py's `_MAX_RANGE_DAYS`. */
export const MAX_CUSTOM_RANGE_DAYS = 366;

export const DATE_RANGE_PRESETS: { key: AnalyticsDateRangePreset; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "last_7_days", label: "Last 7 Days" },
  { key: "last_30_days", label: "Last 30 Days" },
  { key: "last_90_days", label: "Last 90 Days" },
  { key: "custom", label: "Custom Range" },
];

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Client-side validation mirrors only the checks the backend itself
 * enforces (app/analytics/dates.py::resolve_date_range) - missing
 * dates, end before start, and an excessive span. It deliberately does
 * NOT reject a future range: the backend treats a future range as
 * valid and simply returns zero-count data, so the frontend must not
 * invent a stricter rule than the API contract.
 */
export function validateCustomRange(startDate: string, endDate: string): string | null {
  if (!startDate || !endDate) {
    return "Start date and end date are both required for a custom range.";
  }
  if (!DATE_ONLY_PATTERN.test(startDate) || !DATE_ONLY_PATTERN.test(endDate)) {
    return "Dates must be in YYYY-MM-DD format.";
  }
  if (endDate < startDate) {
    return "End date must not be before start date.";
  }
  const spanDays = Math.round((Date.parse(endDate) - Date.parse(startDate)) / 86_400_000) + 1;
  if (spanDays > MAX_CUSTOM_RANGE_DAYS) {
    return `Date range cannot exceed ${MAX_CUSTOM_RANGE_DAYS} days.`;
  }
  return null;
}

/** Formats a plain "YYYY-MM-DD" calendar date for display without ever
 * routing it through UTC parsing, which would risk shifting the
 * displayed day by one when the browser's local timezone is behind UTC. */
export function formatCalendarDate(dateOnly: string): string {
  const parts = dateOnly.split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return dateOnly;
  }
  const [year, month, day] = parts;
  const localDate = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(localDate);
}
