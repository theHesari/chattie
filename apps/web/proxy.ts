import { getSessionCookie } from "better-auth/cookies";
import { type NextRequest, NextResponse } from "next/server";
import { newThreadPath } from "@/lib/routes";

/**
 * Optimistic gate for the chat area: only checks that a session cookie exists.
 * The real check happens on the server (lib/session.ts) and in the API (JWT).
 * Auth pages aren't matched, so an expired cookie can't cause a redirect loop.
 */
export function proxy(request: NextRequest) {
  const redirect = (path: string) =>
    NextResponse.redirect(new URL(path, request.url));

  if (!getSessionCookie(request)) return redirect("/sign-in");
  // Every visit to `/` starts a new thread with its own id.
  if (request.nextUrl.pathname === "/") return redirect(newThreadPath());
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/chat/:path*"],
};
