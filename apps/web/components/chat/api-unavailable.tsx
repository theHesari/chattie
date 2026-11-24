"use client";

import { CloudOffIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRetry } from "@/hooks/use-retry";

/** Shown instead of the chat when the API can't be reached; an expected state, not an error. */
export function ApiUnavailable() {
  const { retry, isRetrying } = useRetry();

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <CloudOffIcon className="size-10 text-muted-foreground" />
      <h2 className="font-medium">Chattie is temporarily unavailable</h2>
      <p className="max-w-sm text-muted-foreground text-sm">
        We couldn't reach the chat service. Your conversations are safe; try
        again in a moment.
      </p>
      <Button disabled={isRetrying} onClick={retry} variant="outline">
        {isRetrying ? "Retrying…" : "Try again"}
      </Button>
    </div>
  );
}
