/** Shapes of the company endpoints (services/llm/company/routes.py). JSON is camelCase. */

export type Role = "employee" | "manager" | "hr" | "admin";

export type RequestKind =
  | "day_off"
  | "sick_day"
  | "remote_day"
  | "schedule_change"
  | "overtime";

export type RequestStatus = "approved" | "rejected" | "cancelled";

export type WorkDayKind = "office" | "remote" | "leave" | "sick" | "holiday";

/** GET /me (null when the account has no character yet) and the result of POST /character. */
export type Character = {
  employeeId: number;
  name: string;
  title: string;
  role: Role;
  department: string;
  managerName: string | null;
};

export type TimelineEvent = {
  happenedAt: string;
  kind: string;
  title: string;
  details: Record<string, unknown>;
};

export type WorkDay = {
  day: string;
  hours: number;
  kind: WorkDayKind;
};

export type LeaveBalance = {
  year: number;
  allowance: number;
  used: number;
  remaining: number;
};

/** GET /me/history */
export type HistoryView = {
  today: string;
  events: TimelineEvent[];
  balance: LeaveBalance;
  recentWorkDays: WorkDay[];
};

/** One row of GET /me/requests. */
export type RequestView = {
  id: number;
  kind: RequestKind;
  startsOn: string;
  endsOn: string;
  startTime: string | null;
  endTime: string | null;
  hours: number | null;
  reason: string | null;
  status: RequestStatus;
  decisionReason: string;
  createdAt: string;
};

/** The instant decision of POST /me/requests or a cancel. `id` is null when the request was malformed. */
export type RequestResult = {
  id: number | null;
  status: RequestStatus;
  decisionReason: string;
  balanceAfter: number | null;
};

/** One direct report in GET /team (managers only). */
export type TeamMember = {
  id: number;
  name: string;
  title: string;
  todayStatus: WorkDayKind | null;
  nextAway: string | null;
};

/** The body of POST /character. */
export type NewCharacter = {
  displayName: string;
  role: Role;
  departmentId: number | null;
};

/** The body of POST /me/requests. `requestKey` makes a retried or double-clicked submit one request. */
export type NewRequest = {
  kind: RequestKind;
  startsOn: string;
  endsOn?: string;
  startTime?: string;
  endTime?: string;
  hours?: number;
  reason?: string;
  requestKey: string;
};
