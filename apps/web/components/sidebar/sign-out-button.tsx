"use client";

import { LogOutIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSignOut } from "@/hooks/use-sign-out";

export function SignOutButton() {
  const { signOut, pending } = useSignOut();

  return (
    <Button
      aria-label="Sign out"
      disabled={pending}
      onClick={signOut}
      size="icon"
      variant="ghost"
    >
      <LogOutIcon />
    </Button>
  );
}
