export function formatNumber(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en").format(value);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Not recorded";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function humanize(value: string | null | undefined): string {
  if (!value) {
    return "Not recorded";
  }
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
