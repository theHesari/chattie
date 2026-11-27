import { useMutation } from "@tanstack/react-query";
import { useRefreshCompany } from "@/hooks/use-refresh-company";
import { cancelRequest, messageFor } from "@/lib/api/company-client";

/** Cancels a request that has not started yet; the balance and lists refresh afterwards. */
export function useUndoRequest() {
  const refresh = useRefreshCompany();
  const mutation = useMutation({
    mutationFn: (id: number) => cancelRequest(id),
    onSuccess: refresh,
  });

  return {
    undo: (id: number) => mutation.mutate(id),
    undoing: mutation.isPending,
    reset: mutation.reset,
    result: mutation.data ?? null,
    error: mutation.error ? messageFor(mutation.error) : null,
  };
}
