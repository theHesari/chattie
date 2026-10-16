import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { MobileNav } from "@/components/sidebar/mobile-nav";
import { SidebarContent } from "@/components/sidebar/sidebar-content";

/** Signed-in area: thread sidebar (desktop) or drawer (mobile) around the chat. */
export default function ChatLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex h-dvh">
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
