import { apiGet, authHeaders } from "@/lib/api/client";
import { describeApiError } from "@/lib/api/errors";
import {
  characterSchema,
  historySchema,
  meSchema,
  requestsSchema,
  resultSchema,
  teamSchema,
} from "@/lib/api/schemas";
import { ApiUnavailableError, apiFetch } from "@/lib/api/shared";
import type {
  Character,
  HistoryView,
  NewCharacter,
  NewRequest,
  RequestResult,
  RequestView,
  TeamMember,
} from "@/types/company";

/** A 4xx answer to a change (file, cancel, create): `message` is already a sentence for the user. */
export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    body: unknown,
    retryAfter: string | null,
  ) {
    super(describeApiError(status, body, retryAfter));
  }
}

/** POST as the signed-in user (browser side). 401 sends the user to sign in; other 4xx become ApiRequestError. */
async function post(path: string, body?: unknown): Promise<unknown> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    window.location.assign("/sign-in");
  }
  if (!response.ok) {
    const parsed = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      parsed,
      response.headers.get("Retry-After"),
    );
  }
  return response.json();
}

export async function fetchMe(): Promise<Character | null> {
  return meSchema.parse(await apiGet("/me"));
}

export async function fetchHistory(): Promise<HistoryView> {
  return historySchema.parse(await apiGet("/me/history"));
}

export async function fetchRequests(): Promise<RequestView[]> {
  return requestsSchema.parse(await apiGet("/me/requests"));
}

export async function fetchTeam(): Promise<TeamMember[]> {
  return teamSchema.parse(await apiGet("/team"));
}

/** Creates the account's character, replacing any earlier one (and its history). */
export async function createCharacter(input: NewCharacter): Promise<Character> {
  return characterSchema.parse(await post("/character", input));
}

/** Files a request; the server decides at once. Reuse `requestKey` when retrying the same attempt. */
export async function fileRequest(input: NewRequest): Promise<RequestResult> {
  return resultSchema.parse(await post("/me/requests", input));
}

export async function cancelRequest(id: number): Promise<RequestResult> {
  return resultSchema.parse(await post(`/me/requests/${id}/cancel`));
}

/** A sentence for the user for any failure of a change: the server's reason, or "unavailable". */
export function messageFor(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof ApiUnavailableError) {
    return "Chattie is temporarily unavailable. Please try again in a moment.";
  }
  return "Something went wrong. Please try again.";
}
