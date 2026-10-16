import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";

/** Sends visitors with a valid session to their chats (reads the session: render inside <Suspense>). */
export async function RedirectIfSignedIn() {
  if (await getSession()) redirect("/");
  return null;
}
