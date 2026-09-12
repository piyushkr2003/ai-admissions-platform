import { describe, expect, it } from "vitest";
import { DATE_RANGE_PRESETS, MAX_CUSTOM_RANGE_DAYS, formatCalendarDate, validateCustomRange } from "@/lib/analytics/date-range";

describe("DATE_RANGE_PRESETS", () => {
  it("offers exactly Today, Last 7/30/90 Days, and Custom Range", () => {
    expect(DATE_RANGE_PRESETS.map((preset) => preset.key)).toEqual([
      "today",
      "last_7_days",
      "last_30_days",
      "last_90_days",
      "custom",
    ]);
  });
});

describe("validateCustomRange", () => {
  it("rejects a missing start or end date", () => {
    expect(validateCustomRange("", "2026-01-10")).toMatch(/required/);
    expect(validateCustomRange("2026-01-01", "")).toMatch(/required/);
  });

  it("rejects end date before start date", () => {
    expect(validateCustomRange("2026-06-10", "2026-06-01")).toMatch(/must not be before/);
  });

  it("accepts a valid same-day range", () => {
    expect(validateCustomRange("2026-06-01", "2026-06-01")).toBeNull();
  });

  it("accepts a valid multi-day range", () => {
    expect(validateCustomRange("2026-06-01", "2026-06-30")).toBeNull();
  });

  it("rejects a range spanning more than the backend's maximum", () => {
    expect(validateCustomRange("2020-01-01", "2026-01-01")).toMatch(new RegExp(`${MAX_CUSTOM_RANGE_DAYS} days`));
  });

  it("does NOT reject a range entirely in the future - the backend treats that as valid and empty", () => {
    expect(validateCustomRange("2099-01-01", "2099-01-31")).toBeNull();
  });
});

describe("formatCalendarDate", () => {
  it("formats a plain calendar date without shifting the day via UTC parsing", () => {
    // Regression guard: new Date("2026-01-01") parses as UTC midnight,
    // which displays as Dec 31 in any timezone behind UTC. The fix
    // parses the Y/M/D components directly instead.
    expect(formatCalendarDate("2026-01-01")).toBe("Jan 1");
    expect(formatCalendarDate("2026-12-31")).toBe("Dec 31");
  });
});
