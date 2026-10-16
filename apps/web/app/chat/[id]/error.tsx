"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import type { RouteErrorProps } from "@/types/chat";

export default function ChatError({ error, retry }: RouteErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <h2 className="font-medium">Couldn't load this conversation</h2>
      <p className="text-muted-foreground text-sm">
        Check that the Chattie API is running, then try again.
      </p>
      <Button onClick={retry} variant="outline">
        Try again
      </Button>
    </div>
  );
}
