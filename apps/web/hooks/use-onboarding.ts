import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createCharacter, messageFor } from "@/lib/api/company-client";
import { newThreadPath } from "@/lib/routes";
import type { NewCharacter } from "@/types/company";

/** Creates the character; on success opens a fresh chat as that character. */
export function useOnboarding() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (input: NewCharacter) => createCharacter(input),
    onSuccess: () => {
      queryClient.clear(); // a new character: nothing cached about the old one may carry over
      router.push(newThreadPath());
    },
  });

  return {
    submit: (input: NewCharacter) => mutation.mutate(input),
    error: mutation.error ? messageFor(mutation.error) : null,
    // Stay "pending" through the redirect so the button can't be pressed twice.
    pending: mutation.isPending || mutation.isSuccess,
    succeeded: mutation.isSuccess,
    reset: mutation.reset,
  };
}
