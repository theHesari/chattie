"use client";

import { MenuIcon } from "lucide-react";
import { NewChatButton } from "@/components/sidebar/new-chat-button";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useMobileNav } from "@/hooks/use-mobile-nav";
import type { MobileNavProps } from "@/types/sidebar";

/** Small-screen header; the chat history opens in a drawer from the left. */
export function MobileNav({ children }: MobileNavProps) {
  const { open, onOpenChange, closeOnNavigate } = useMobileNav();

  return (
    <header className="flex items-center gap-2 border-b px-2 py-2 md:hidden">
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetTrigger asChild>
          <Button aria-label="Open chat history" size="icon" variant="ghost">
            <MenuIcon />
          </Button>
        </SheetTrigger>
        <SheetContent
          className="flex w-72 flex-col gap-0 p-0"
          onClick={closeOnNavigate}
          // Its corner "×" would sit on top of "New chat"; the overlay, Esc and any link close it.
          showCloseButton={false}
          side="left"
        >
          <SheetTitle className="sr-only">Chat history</SheetTitle>
          {children}
        </SheetContent>
      </Sheet>
      <span className="font-semibold">Chattie</span>
      <div className="ml-auto">
        <NewChatButton />
      </div>
    </header>
  );
}
