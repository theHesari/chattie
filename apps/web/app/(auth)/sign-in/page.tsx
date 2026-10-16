import type { Metadata } from "next";
import { AuthForm } from "@/components/auth/auth-form";

export const metadata: Metadata = { title: "Sign in · Chattie" };

export default function SignInPage() {
  return <AuthForm mode="sign-in" />;
}
