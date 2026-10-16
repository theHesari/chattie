import { useParams } from "next/navigation";

/** Id of the thread open in /chat/[id], or undefined on any other route. */
export function useActiveThreadId(): string | undefined {
  const params = useParams<{ id?: string }>();
  return params.id;
}
