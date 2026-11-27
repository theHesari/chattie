import {
  dehydrate,
  HydrationBoundary,
  QueryClient,
} from "@tanstack/react-query";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ApiUnavailable } from "@/components/chat/api-unavailable";
import { CharacterHeader } from "@/components/dashboard/character-header";
import { HoursBars } from "@/components/dashboard/hours-bars";
import { LeaveCard } from "@/components/dashboard/leave-card";
import { RequestForm } from "@/components/dashboard/request-form";
import { RequestList } from "@/components/dashboard/request-list";
import { TeamTable } from "@/components/dashboard/team-table";
import { Timeline } from "@/components/dashboard/timeline";
import {
  getHistory,
  getMe,
  getRequests,
  getTeam,
  NoCharacterError,
} from "@/lib/api/company";
import { ApiUnavailableError } from "@/lib/api/shared";
import { historyKey, meKey, requestsKey, teamKey } from "@/lib/queries/company";
import { ONBOARDING_PATH } from "@/lib/routes";

export const metadata: Metadata = { title: "Dashboard · Chattie" };

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <p className="animate-pulse text-muted-foreground text-sm">
            Loading your dashboard…
          </p>
        </div>
      }
    >
      <Dashboard />
    </Suspense>
  );
}

/** Seeds the browser's company queries with server data; TanStack Query owns them from then on. */
async function Dashboard() {
  try {
    const character = await getMe();
    if (!character) redirect(ONBOARDING_PATH);
    const isManager = character.role === "manager";
    const [history, requests, team] = await Promise.all([
      getHistory(),
      getRequests(),
      isManager ? getTeam() : Promise.resolve(null),
    ]);

    const queryClient = new QueryClient();
    queryClient.setQueryData(meKey, character);
    queryClient.setQueryData(historyKey, history);
    queryClient.setQueryData(requestsKey, requests);
    if (team) queryClient.setQueryData(teamKey, team);

    return (
      <HydrationBoundary state={dehydrate(queryClient)}>
        <div className="h-full overflow-y-auto">
          <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
            <CharacterHeader character={character} />
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
              <LeaveCard />
              <RequestForm />
            </div>
            <HoursBars />
            {isManager && <TeamTable />}
            <div className="grid gap-4 md:grid-cols-2">
              <RequestList />
              <Timeline />
            </div>
          </div>
        </div>
      </HydrationBoundary>
    );
  } catch (error) {
    // No character yet (409) means onboarding; the API being down is expected; redirect() must pass through.
    if (error instanceof NoCharacterError) redirect(ONBOARDING_PATH);
    if (error instanceof ApiUnavailableError) return <ApiUnavailable />;
    throw error;
  }
}
