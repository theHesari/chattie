/**
 * Turns an API failure into a sentence for the user. Pure: no imports, so Node's test runner can load it.
 * Never shows raw JSON, a status code, or a stack trace.
 */

type ErrorBody = { detail?: unknown } | null | undefined;

const GENERIC = "Something went wrong. Please try again.";

function detailOf(body: unknown): unknown {
  return (body as ErrorBody)?.detail;
}

function firstMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (typeof first?.msg === "string") return first.msg;
  }
  return null;
}

export function describeApiError(
  status: number,
  body: unknown,
  retryAfter?: string | null,
): string {
  const message = firstMessage(detailOf(body));

  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 429) {
    return retryAfter
      ? `Too many requests. Please wait ${retryAfter} seconds and try again.`
      : "Too many requests. Please wait a moment and try again.";
  }
  if (status === 503)
    return "This part of Chattie isn't set up on the server yet.";
  if (status >= 500)
    return "Something went wrong on our side. Please try again.";
  if (status === 409) {
    if (message && /changed/i.test(message)) {
      return "Your character changed while this was running. Reload the page and try again.";
    }
    if (message && /limit/i.test(message)) {
      return "Chattie has reached its limit of active characters. Please try again later.";
    }
    return "You don't have a character yet. Create one to continue.";
  }
  if (status === 422) {
    return message ?? "Please check what you entered and try again.";
  }
  return GENERIC;
}
