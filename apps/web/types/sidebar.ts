import type { ReactNode } from "react";

export type SidebarMessageProps = {
  text: string;
};

export type MobileNavProps = {
  /** The drawer's content: the same SidebarContent the desktop sidebar renders. */
  children: ReactNode;
};
