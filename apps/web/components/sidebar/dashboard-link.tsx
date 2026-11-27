"use client";

import { LayoutDashboardIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DASHBOARD_PATH } from "@/lib/routes";
import { cn } from "@/lib/utils";

const LINK_CLASS =
  "flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-muted";

/** The same link without the "current page" highlight: shown while the path is still unknown (prerender). */
export function DashboardLinkFallback() {
  return (
    <Link className={LINK_CLASS} href={DASHBOARD_PATH}>
      <LayoutDashboardIcon className="size-4" />
      My dashboard
    </Link>
  );
}

/** Reads the current path, so render it inside <Suspense fallback={<DashboardLinkFallback />}>. */
export function DashboardLink() {
  const active = usePathname() === DASHBOARD_PATH;

  return (
    <Link
      aria-current={active ? "page" : undefined}
      className={cn(LINK_CLASS, active && "bg-muted font-medium")}
      href={DASHBOARD_PATH}
    >
      <LayoutDashboardIcon className="size-4" />
      My dashboard
    </Link>
  );
}
