import { describe, expect, it } from "vitest";
import { validateComparisonInput } from "../validation";

describe("validateComparisonInput", () => {
  it("accepts two distinct, well-formed NCT numbers", () => {
    expect(validateComparisonInput("NCT00000001", "NCT00000002")).toBeNull();
  });

  it("is case-insensitive about the NCT prefix", () => {
    expect(validateComparisonInput("nct00000001", "nct00000002")).toBeNull();
  });

  it("rejects empty input", () => {
    expect(validateComparisonInput("", "NCT00000002")).toMatch(/enter both/i);
    expect(validateComparisonInput("NCT00000001", "")).toMatch(/enter both/i);
    expect(validateComparisonInput("   ", "NCT00000002")).toMatch(/enter both/i);
  });

  it("rejects a malformed NCT number", () => {
    expect(validateComparisonInput("NCT123", "NCT00000002")).toMatch(/nct/i);
    expect(validateComparisonInput("NCT00000001", "not-an-id")).toMatch(/nct/i);
  });

  it("rejects comparing a trial against itself", () => {
    expect(validateComparisonInput("NCT00000001", "NCT00000001")).toMatch(/different/i);
  });

  it("rejects the same trial entered with different casing", () => {
    expect(validateComparisonInput("nct00000001", "NCT00000001")).toMatch(/different/i);
  });
});
