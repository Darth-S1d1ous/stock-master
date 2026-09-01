import { describe, expect, it } from "vitest";
import { formatMetric } from "@/lib/format";

describe("formatMetric", () => {
  it("preserves percentage semantics", () => {
    expect(formatMetric("-6.125", "daily_price_change_percent")).toBe("-6.13%");
  });

  it("does not render invalid numbers as NaN", () => {
    expect(formatMetric("not-a-number", "pe_ratio")).toBe("not-a-number");
  });

  it("renders missing observations consistently", () => {
    expect(formatMetric(null, "pe_ratio")).toBe("—");
  });
});
