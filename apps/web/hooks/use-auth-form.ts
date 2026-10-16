import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { authClient } from "@/lib/auth-client";
import type { AuthMode } from "@/types/auth";

const field = (form: FormData, name: string) =>
  String(form.get(name) ?? "").trim();

async function authenticate(mode: AuthMode, form: FormData) {
  const email = field(form, "email");
  const password = String(form.get("password") ?? "");
  const { error } =
    mode === "sign-up"
      ? await authClient.signUp.email({
          name: field(form, "name"),
          email,
          password,
        })
      : await authClient.signIn.email({ email, password });
  if (error) {
    throw new Error(error.message ?? "Something went wrong. Please try again.");
  }
}

/** Sign-in / sign-up form as a mutation; on success opens a fresh chat. */
export function useAuthForm(mode: AuthMode) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (form: FormData) => authenticate(mode, form),
    onSuccess: () => {
      queryClient.clear(); // a new user: nothing cached may carry over
      router.push("/");
    },
  });

  // A plain onSubmit (not <form action>): React resets action forms after they run,
  // which would wipe the email the user typed when sign-in fails.
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    mutation.mutate(new FormData(event.currentTarget));
  };

  return {
    submit,
    error: mutation.error?.message ?? null,
    // Stay "pending" through the redirect so the button can't be pressed twice.
    pending: mutation.isPending || mutation.isSuccess,
  };
}
