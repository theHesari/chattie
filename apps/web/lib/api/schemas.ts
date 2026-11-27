import { z } from "zod";
import type {
  Character,
  HistoryView,
  RequestResult,
  RequestView,
  TeamMember,
} from "@/types/company";

// No `@/` imports at runtime here: Node's test runner loads this file directly (see schemas.test.mjs).

const role = z.enum(["employee", "manager", "hr", "admin"]);
const requestKind = z.enum([
  "day_off",
  "sick_day",
  "remote_day",
  "schedule_change",
  "overtime",
]);
const requestStatus = z.enum(["approved", "rejected", "cancelled"]);
const workDayKind = z.enum(["office", "remote", "leave", "sick", "holiday"]);

export const characterSchema: z.ZodType<Character> = z.object({
  employeeId: z.number(),
  name: z.string(),
  title: z.string(),
  role,
  department: z.string(),
  managerName: z.string().nullable(),
});

/** GET /me answers null for an account without a character. */
export const meSchema: z.ZodType<Character | null> = characterSchema.nullable();

export const historySchema: z.ZodType<HistoryView> = z.object({
  today: z.string(),
  events: z.array(
    z.object({
      happenedAt: z.string(),
      kind: z.string(),
      title: z.string(),
      details: z.record(z.string(), z.unknown()),
    }),
  ),
  balance: z.object({
    year: z.number(),
    allowance: z.number(),
    used: z.number(),
    remaining: z.number(),
  }),
  recentWorkDays: z.array(
    z.object({ day: z.string(), hours: z.number(), kind: workDayKind }),
  ),
});

export const requestsSchema: z.ZodType<RequestView[]> = z.array(
  z.object({
    id: z.number(),
    kind: requestKind,
    startsOn: z.string(),
    endsOn: z.string(),
    startTime: z.string().nullable(),
    endTime: z.string().nullable(),
    hours: z.number().nullable(),
    reason: z.string().nullable(),
    status: requestStatus,
    decisionReason: z.string(),
    createdAt: z.string(),
  }),
);

export const resultSchema: z.ZodType<RequestResult> = z.object({
  id: z.number().nullable(),
  status: requestStatus,
  decisionReason: z.string(),
  balanceAfter: z.number().nullable(),
});

export const teamSchema: z.ZodType<TeamMember[]> = z.array(
  z.object({
    id: z.number(),
    name: z.string(),
    title: z.string(),
    todayStatus: workDayKind.nullable(),
    nextAway: z.string().nullable(),
  }),
);
