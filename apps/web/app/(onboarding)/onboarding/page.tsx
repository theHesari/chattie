import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ApiUnavailable } from "@/components/chat/api-unavailable";
import { OnboardingForm } from "@/components/onboarding/onboarding-form";
import { getMe } from "@/lib/api/company";
import { ApiUnavailableError } from "@/lib/api/shared";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Your character · Chattie" };

export default function OnboardingPage({
  searchParams,
}: PageProps<"/onboarding">) {
  return (
    <Suspense
      fallback={
        <p className="animate-pulse text-muted-foreground text-sm">Loading…</p>
      }
    >
      <OnboardingContent searchParams={searchParams} />
    </Suspense>
  );
}

async function OnboardingContent({
  searchParams,
}: Pick<PageProps<"/onboarding">, "searchParams">) {
  const [{ change }, user] = await Promise.all([searchParams, requireUser()]);

  let hasCharacter: boolean;
  try {
    hasCharacter = (await getMe()) !== null;
  } catch (error) {
    if (error instanceof ApiUnavailableError) return <ApiUnavailable />;
    throw error;
  }
  // Someone who already has a character only comes back here on purpose (?change=1).
  if (hasCharacter && change !== "1") redirect("/");
  return <OnboardingForm defaultName={user.name} replacing={hasCharacter} />;
}
