import { DefaultChatTransport, type UIMessage } from "ai";
import { ApiError, apiFetch, apiUrl, threadsSchema } from "@/lib/api/shared";
import { authClient } from "@/lib/auth-client";
import type { ThreadSummary } from "@/types/thread";

/** Fresh short-lived JWT per request (Better Auth JWT plugin). */
export async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await authClient.token();
  return data ? { Authorization: `Bearer ${data.token}` } : {};
}

/** GET from the API as the signed-in user (browser side). Throws ApiError on failure. */
export async function apiGet(path: string): Promise<unknown> {
  const response = await apiFetch(path, { headers: await authHeaders() });
  if (!response.ok) throw new ApiError(response.status, path);
  return response.json();
}

/** The user's most recently active threads, newest first. */
export async function fetchThreads(): Promise<ThreadSummary[]> {
  return threadsSchema.parse(await apiGet("/threads"));
}

/**
 * Streams replies from POST /chat. Only the newest message is sent:
 * the server already keeps the rest of the thread in its checkpointer.
 */
export function createChatTransport() {
  return new DefaultChatTransport<UIMessage>({
    api: apiUrl("/chat"),
    headers: authHeaders,
    prepareSendMessagesRequest: ({ id, messages, headers }) => ({
      body: { id, message: messages.at(-1) },
      headers,
    }),
  });
}
