import { type NextRequest, NextResponse } from "next/server";
import { newThreadPath } from "@/lib/routes";

/** Every visit to `/` starts a new thread with its own id. */
export function proxy(request: NextRequest) {
  return NextResponse.redirect(new URL(newThreadPath(), request.url));
}

export const config = {
  matcher: "/",
};
