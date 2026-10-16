import { useRouter } from "next/navigation";
import { newThreadPath } from "@/lib/routes";

/**
 * Opens a fresh thread and re-fetches the sidebar's thread list.
 * The list lives in the root layout, which a plain navigation doesn't re-render.
 */
export function useNewChat() {
  const router = useRouter();

  return () => {
    router.push(newThreadPath());
    router.refresh();
  };
}
