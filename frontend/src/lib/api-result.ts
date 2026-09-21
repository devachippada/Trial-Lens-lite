/**
 * Pure response-parsing logic, factored out of the actual fetch calls
 * in lib/api.ts so it's unit-testable without a network stack or a
 * running backend — see src/lib/__tests__/api-result.test.ts.
 *
 * FastAPI reports errors as either `{"detail": "message"}`
 * (HTTPException, e.g. the 404 from POST /api/v1/compare) or
 * `{"detail": [{"msg": ..., "loc": [...]}]}` (a pydantic validation
 * error, on a 422). Both are normalized to one human-readable string
 * here so every page only has one error shape to render.
 */

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string; status: number };

interface FastApiValidationError {
  msg?: string;
  loc?: (string | number)[];
}

function extractDetailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const validationError = item as FastApiValidationError;
          const field = Array.isArray(validationError.loc) ? validationError.loc.at(-1) : undefined;
          return field !== undefined ? `${field}: ${validationError.msg}` : validationError.msg ?? null;
        }
        return null;
      })
      .filter((message): message is string => Boolean(message));

    return messages.length > 0 ? messages.join("; ") : null;
  }

  return null;
}

/**
 * Turn a fetch response's status/ok/raw body text into a typed
 * `ApiResult`. Never throws — a body that isn't valid JSON, or is JSON
 * but has no recognizable shape, becomes a generic-but-useful error
 * message rather than an uncaught exception reaching a page.
 */
export function parseApiResponse<T>(status: number, ok: boolean, bodyText: string): ApiResult<T> {
  let parsed: unknown;
  let parseFailed = false;

  if (bodyText.length > 0) {
    try {
      parsed = JSON.parse(bodyText);
    } catch {
      parseFailed = true;
    }
  }

  if (ok) {
    if (parseFailed) {
      return { ok: false, error: "The server returned a response that wasn't valid JSON.", status };
    }
    return { ok: true, data: parsed as T };
  }

  const detailMessage =
    !parseFailed && parsed && typeof parsed === "object" && "detail" in parsed
      ? extractDetailMessage((parsed as { detail: unknown }).detail)
      : null;

  return {
    ok: false,
    error: detailMessage ?? `Request failed with status ${status}.`,
    status,
  };
}
