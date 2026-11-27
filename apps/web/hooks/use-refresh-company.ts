import { useQueryClient } from "@tanstack/react-query";
import { historyKey, requestsKey, teamKey } from "@/lib/queries/company";

/** After a request changes, everything that shows it (balance, list, timeline, team) refetches. */
export function useRefreshCompany() {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of [historyKey, requestsKey, teamKey]) {
      queryClient.invalidateQueries({ queryKey });
    }
  };
}
