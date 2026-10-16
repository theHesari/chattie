"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthForm } from "@/hooks/use-auth-form";
import type { AuthFormProps } from "@/types/auth";

const COPY = {
  "sign-in": {
    title: "Sign in to Chattie",
    submit: "Sign in",
    switchText: "No account yet?",
    switchLink: { href: "/sign-up", label: "Create one" },
  },
  "sign-up": {
    title: "Create your account",
    submit: "Create account",
    switchText: "Already have an account?",
    switchLink: { href: "/sign-in", label: "Sign in" },
  },
} as const;

export function AuthForm({ mode }: AuthFormProps) {
  const { submit, error, pending } = useAuthForm(mode);
  const copy = COPY[mode];

  return (
    <form className="flex w-full max-w-sm flex-col gap-4" onSubmit={submit}>
      <h1 className="font-semibold text-xl">{copy.title}</h1>
      {mode === "sign-up" && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name">Name</Label>
          <Input autoComplete="name" id="name" name="name" required />
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          autoComplete="email"
          id="email"
          name="email"
          required
          type="email"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          autoComplete={
            mode === "sign-up" ? "new-password" : "current-password"
          }
          id="password"
          minLength={8}
          name="password"
          required
          type="password"
        />
      </div>
      {error && (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      )}
      <Button disabled={pending} type="submit">
        {pending ? "Please wait…" : copy.submit}
      </Button>
      <p className="text-center text-muted-foreground text-sm">
        {copy.switchText}{" "}
        <Link className="text-foreground underline" href={copy.switchLink.href}>
          {copy.switchLink.label}
        </Link>
      </p>
    </form>
  );
}
