import "server-only";
import { cache } from "react";
import {
  historySchema,
  meSchema,
  requestsSchema,
  teamSchema,
} from "@/lib/api/schemas";
import { apiGet } from "@/lib/api/server";
import { ApiError } from "@/lib/api/shared";
import type {
  Character,
  HistoryView,
  RequestView,
  TeamMember,
} from "@/types/company";

/** The account has no character yet (HTTP 409): send it to onboarding. */
export class NoCharacterError extends Error {
  constructor() {
    super("no character yet");
  }
}

/** Runs a company GET; a 409 means "no character" and becomes NoCharacterError. */
async function companyGet(path: string): Promise<unknown> {
  try {
    return await apiGet(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      throw new NoCharacterError();
    }
    throw error;
  }
}

/** The signed-in user's character, or null before onboarding (server side). */
export const getMe = cache(async (): Promise<Character | null> => {
  return meSchema.parse(await apiGet("/me"));
});

export async function getHistory(): Promise<HistoryView> {
  return historySchema.parse(await companyGet("/me/history"));
}

export async function getRequests(): Promise<RequestView[]> {
  return requestsSchema.parse(await companyGet("/me/requests"));
}

/** The manager's direct reports; the API answers 403 for everyone else. */
export async function getTeam(): Promise<TeamMember[]> {
  return teamSchema.parse(await companyGet("/team"));
}
