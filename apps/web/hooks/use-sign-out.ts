import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authClient } from "@/lib/auth-client";

async function signOut() {
  const { error } = await authClient.signOut();
  if (error) throw new Error(error.message ?? "Couldn't sign out.");
}

export function useSignOut() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: signOut,
    onSuccess: () => {
      queryClient.clear();
      // Full page load, not router.push: Next keeps recently visited pages mounted
      // (React <Activity>), and those still hold the previous user's chats.
      window.location.assign("/sign-in");
    },
  });

  return {
    signOut: () => mutation.mutate(),
    pending: mutation.isPending || mutation.isSuccess,
  };
}
