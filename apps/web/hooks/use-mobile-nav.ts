import { type MouseEvent, useState } from "react";

/**
 * Open state for the mobile drawer. Every link and button in the drawer navigates
 * (a thread, "New chat"), so any click on one closes it. This deliberately avoids
 * reading the URL: usePathname() in the root layout would block prerendering under
 * Cache Components.
 */
export function useMobileNav() {
  const [open, setOpen] = useState(false);

  const closeOnNavigate = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as Element).closest("a, button")) setOpen(false);
  };

  return { open, onOpenChange: setOpen, closeOnNavigate };
}
