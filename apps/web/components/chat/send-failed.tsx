import { RotateCcwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SendFailedProps } from "@/types/chat";

/** Inline notice when a reply couldn't be fetched (e.g. the API is down), with a one-click resend. */
export function SendFailed({ onRetry }: SendFailedProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-3 text-muted-foreground text-sm"
      role="alert"
    >
      Couldn't reach Chattie, so your last message wasn't answered.
      <Button onClick={onRetry} size="sm" variant="outline">
        <RotateCcwIcon />
        Retry
      </Button>
    </div>
  );
}
