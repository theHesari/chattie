import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { threadsKey } from "@/lib/queries/threads";
import { newThreadPath } from "@/lib/routes";

/** Opens a fresh thread and refetches the thread list (it may have changed elsewhere). */
export function useNewChat() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return () => {
    router.push(newThreadPath());
    queryClient.invalidateQueries({ queryKey: threadsKey });
  };
}
