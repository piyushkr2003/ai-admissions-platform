import { describe, expect, it } from "vitest";
import { toQueryString } from "@/lib/api/query";

describe("toQueryString", () => {
  it("returns an empty string when nothing is set", () => {
    expect(toQueryString({})).toBe("");
    expect(toQueryString({ college_id: undefined, status: null, search: "" })).toBe("");
  });

  it("serializes only defined, non-empty values", () => {
    const query = toQueryString({ college_id: "college-1", page: 2, active: false });
    expect(query).toBe("?college_id=college-1&page=2&active=false");
  });
});
