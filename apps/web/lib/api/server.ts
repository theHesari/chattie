import "server-only";
import { type UIMessage, validateUIMessages } from "ai";
import { notFound, redirect } from "next/navigation";
import { ApiError, apiFetch, threadsSchema } from "@/lib/api/shared";
import { getApiToken } from "@/lib/session";
import type { ThreadSummary } from "@/types/thread";

/** GET from the API as the signed-in user (server side). */
export async function apiGet(path: string): Promise<unknown> {
  const response = await apiFetch(path, {
    headers: { Authorization: `Bearer ${await getApiToken()}` },
  });
  if (response.status === 401) redirect("/sign-in");
  if (response.status === 404) notFound(); // missing, or someone else's thread
  if (!response.ok) throw new ApiError(response.status, path);
  return response.json();
}

/** The user's most recently active threads, newest first. */
export async function getThreads(): Promise<ThreadSummary[]> {
  return threadsSchema.parse(await apiGet("/threads"));
}

/** A thread's stored history (empty for a new thread). */
export async function getThreadMessages(
  threadId: string,
): Promise<UIMessage[]> {
  const messages = (await apiGet(`/threads/${threadId}/messages`)) as unknown[];
  return messages.length === 0 ? [] : validateUIMessages({ messages });
}
