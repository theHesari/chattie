import { redirect } from "next/navigation";
import { Suspense } from "react";
import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { MobileNav } from "@/components/sidebar/mobile-nav";
import { SidebarContent } from "@/components/sidebar/sidebar-content";
import { getMe } from "@/lib/api/company";
import { ApiUnavailableError } from "@/lib/api/shared";
import { ONBOARDING_PATH } from "@/lib/routes";

/**
 * Sends an account without a character to onboarding (reads the session: render inside <Suspense>).
 * If the API is down it does nothing: the pages show their own "unavailable" state, so there is no redirect loop.
 */
async function CharacterGate() {
  try {
    if ((await getMe()) === null) redirect(ONBOARDING_PATH);
  } catch (error) {
    if (!(error instanceof ApiUnavailableError)) throw error; // includes redirect()
  }
  return null;
}

/** Signed-in area: thread sidebar (desktop) or drawer (mobile) around the chat. */
export default function ChatLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex h-dvh">
      <Suspense>
        <CharacterGate />
      </Suspense>
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav>
          <SidebarContent />
        </MobileNav>
        <main className="min-h-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
