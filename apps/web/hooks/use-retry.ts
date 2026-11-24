import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { threadsKey } from "@/lib/queries/threads";

/** Re-requests the server-rendered page and the thread list, e.g. after the API was unreachable. */
export function useRetry() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [isRetrying, startTransition] = useTransition();

  const retry = () =>
    startTransition(() => {
      router.refresh();
      queryClient.invalidateQueries({ queryKey: threadsKey });
    });

  return { retry, isRetrying };
}
