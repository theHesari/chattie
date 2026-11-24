import { z } from "zod";
import { env } from "@/lib/env";
import type { ThreadSummary } from "@/types/thread";

/** Must match THREAD_ID_PATTERN in services/llm/core_llm/threads.py. */
export const THREAD_ID_PATTERN = /^[\w-]{1,128}$/;

export const apiUrl = (path: string) =>
  new URL(path, env.NEXT_PUBLIC_API_URL).toString();

/** A non-2xx response from the API; `status` drives redirects (401) and not-found (404). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    path: string,
  ) {
    super(`GET ${path} failed: ${status}`);
  }
}

/** The API can't be reached or is failing (down, restarting, 5xx): an expected state, not a bug. */
export class ApiUnavailableError extends Error {
  constructor(path: string) {
    super(`API unavailable: ${path}`);
  }
}

/** fetch() against the API. Connection failures and 5xx responses become ApiUnavailableError. */
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch {
    throw new ApiUnavailableError(path); // refused, reset, DNS: the server isn't there
  }
  if (response.status >= 500) throw new ApiUnavailableError(path);
  return response;
}

export const threadsSchema: z.ZodType<ThreadSummary[]> = z.array(
  z.object({ id: z.string(), title: z.string(), updatedAt: z.string() }),
);
