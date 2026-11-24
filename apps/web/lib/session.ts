import "server-only";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

/**
 * Data Access Layer: the only place that reads the session on the server.
 * Reads request headers, so callers must sit inside a <Suspense> boundary.
 */
export async function getSession() {
  return auth.api.getSession({ headers: await headers() });
}

/** The signed-in user; redirects to /sign-in when there is no valid session. */
export async function requireUser() {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  return session.user;
}

/** Short-lived JWT for calling the FastAPI service on the user's behalf. */
export async function getApiToken(): Promise<string> {
  await requireUser();
  const { token } = await auth.api.getToken({ headers: await headers() });
  return token;
}
