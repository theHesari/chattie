import { SidebarContent } from "@/components/sidebar/sidebar-content";

/** Desktop sidebar (md and up); small screens use MobileNav instead. */
export function AppSidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r bg-muted/30 md:flex">
      <SidebarContent />
    </aside>
  );
}
