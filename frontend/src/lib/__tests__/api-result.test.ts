import { describe, expect, it } from "vitest";
import { parseApiResponse } from "../api-result";

describe("parseApiResponse", () => {
  it("returns ok data for a successful JSON response", () => {
    const result = parseApiResponse<{ hello: string }>(200, true, JSON.stringify({ hello: "world" }));
    expect(result).toEqual({ ok: true, data: { hello: "world" } });
  });

  it("treats an empty successful body as ok with undefined data", () => {
    const result = parseApiResponse(204, true, "");
    expect(result.ok).toBe(true);
  });

  it("reports a generic error when a successful response isn't valid JSON", () => {
    const result = parseApiResponse(200, true, "not json");
    expect(result).toEqual({
      ok: false,
      error: "The server returned a response that wasn't valid JSON.",
      status: 200,
    });
  });

  it("extracts a string detail message from an HTTPException-style error", () => {
    const result = parseApiResponse(404, false, JSON.stringify({ detail: "Trial 'NCT1' not found" }));
    expect(result).toEqual({ ok: false, error: "Trial 'NCT1' not found", status: 404 });
  });

  it("extracts and joins messages from a pydantic validation error (422)", () => {
    const body = JSON.stringify({
      detail: [
        { msg: "field required", loc: ["body", "question"] },
        { msg: "ensure this value has at least 1 characters", loc: ["body", "nct_id_a"] },
      ],
    });
    const result = parseApiResponse(422, false, body);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBe(
        "question: field required; nct_id_a: ensure this value has at least 1 characters"
      );
    }
  });

  it("falls back to a generic message when the error body has no detail field", () => {
    const result = parseApiResponse(500, false, JSON.stringify({ oops: true }));
    expect(result).toEqual({ ok: false, error: "Request failed with status 500.", status: 500 });
  });

  it("falls back to a generic message when the error body isn't valid JSON", () => {
    const result = parseApiResponse(502, false, "<html>Bad Gateway</html>");
    expect(result).toEqual({ ok: false, error: "Request failed with status 502.", status: 502 });
  });

  it("falls back to a generic message for an empty error body", () => {
    const result = parseApiResponse(503, false, "");
    expect(result).toEqual({ ok: false, error: "Request failed with status 503.", status: 503 });
  });
});
