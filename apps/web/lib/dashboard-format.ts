/** Pure helpers for the dashboard: labels, dates, bar scaling and building a request from form values. */
import type {
  NewRequest,
  RequestKind,
  RequestStatus,
  WorkDay,
  WorkDayKind,
} from "@/types/company";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const REQUEST_LABELS: Record<RequestKind, string> = {
  day_off: "Day off",
  sick_day: "Sick day",
  remote_day: "Remote day",
  schedule_change: "Schedule change",
  overtime: "Overtime",
};

const WORK_LABELS: Record<WorkDayKind, string> = {
  office: "Office",
  remote: "Remote",
  leave: "Leave",
  sick: "Sick",
  holiday: "Holiday",
};

/** The kinds in the order the form offers them. */
export const REQUEST_KINDS: readonly RequestKind[] = [
  "day_off",
  "remote_day",
  "sick_day",
  "schedule_change",
  "overtime",
];

export const kindLabel = (kind: RequestKind): string => REQUEST_LABELS[kind];
export const workKindLabel = (kind: WorkDayKind): string => WORK_LABELS[kind];

export function statusTone(status: RequestStatus): "good" | "bad" | "muted" {
  if (status === "approved") return "good";
  if (status === "rejected") return "bad";
  return "muted";
}

/** "2026-12-07" as numbers, without time-zone shifting (these are calendar dates, not instants). */
function parts(iso: string): [number, number, number] {
  const [year, month, day] = iso.split("-").map(Number);
  return [year, month, day];
}

function formatDate(iso: string, withYear: boolean): string {
  const [year, month, day] = parts(iso);
  return `${day} ${MONTHS[month - 1]}${withYear ? ` ${year}` : ""}`;
}

/** "Mon 7 Dec" */
export function weekdayLabel(iso: string): string {
  const [year, month, day] = parts(iso);
  const weekday =
    WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday} ${formatDate(iso, false)}`;
}

/** "7 Dec", "7 Dec to 9 Dec", or with years when the range crosses one. */
export function formatDateRange(startsOn: string, endsOn: string): string {
  if (startsOn === endsOn) return formatDate(startsOn, false);
  const crossesYear = parts(startsOn)[0] !== parts(endsOn)[0];
  return `${formatDate(startsOn, crossesYear)} to ${formatDate(endsOn, crossesYear)}`;
}

export type Bar = {
  day: string;
  percent: number;
  kind: WorkDayKind;
  label: string;
};

const spoken = (hours: number) =>
  Number.isInteger(hours) ? String(hours) : hours.toFixed(1);

/** Bars for the hours chart, oldest first, each scaled 0-100 against `maxHours` and clamped. */
export function barHeights(days: WorkDay[], maxHours = 10): Bar[] {
  return [...days]
    .sort((a, b) => a.day.localeCompare(b.day))
    .map(({ day, hours, kind }) => {
      const safe = Number.isFinite(hours) && hours > 0 ? hours : 0;
      const percent = Math.min(100, Math.round((safe / maxHours) * 100));
      const kindText = workKindLabel(kind).toLowerCase();
      const label =
        safe === 0
          ? `${weekdayLabel(day)}: ${kindText}`
          : `${weekdayLabel(day)}: ${spoken(safe)} h, ${kindText}`;
      return { day, percent, kind, label };
    });
}

/** An approved request that has not started yet can be undone. */
export function canUndo(
  request: { status: RequestStatus; startsOn: string },
  today: string,
): boolean {
  return request.status === "approved" && request.startsOn > today;
}

export type KindFields = {
  endDate: boolean;
  times: boolean;
  hours: boolean;
  reason: boolean;
};

/** Which optional inputs a kind of request uses (a sick day never stores a reason). */
export function fieldsFor(kind: RequestKind): KindFields {
  switch (kind) {
    case "sick_day":
      return { endDate: true, times: false, hours: false, reason: false };
    case "schedule_change":
      return { endDate: true, times: true, hours: false, reason: true };
    case "overtime":
      return { endDate: false, times: false, hours: true, reason: true };
    default:
      return { endDate: true, times: false, hours: false, reason: true };
  }
}

export type RequestFormValues = {
  startsOn: string;
  endsOn: string;
  startTime: string;
  endTime: string;
  hours: string;
  reason: string;
};

/** The API body for a kind from the raw form strings: only the fields the kind uses, and only if filled in. */
export function buildRequest(
  kind: RequestKind,
  values: RequestFormValues,
  requestKey: string,
): NewRequest {
  const fields = fieldsFor(kind);
  const request: NewRequest = { kind, startsOn: values.startsOn, requestKey };
  if (fields.endDate && values.endsOn) request.endsOn = values.endsOn;
  if (fields.times) {
    if (values.startTime) request.startTime = values.startTime;
    if (values.endTime) request.endTime = values.endTime;
  }
  if (fields.hours && values.hours.trim() !== "") {
    const hours = Number(values.hours);
    if (Number.isFinite(hours)) request.hours = hours;
  }
  const reason = values.reason.trim();
  if (fields.reason && reason) request.reason = reason;
  return request;
}

/**
 * The key for the next submit: a new one once the server has decided the current attempt (approved or
 * rejected), the same one otherwise, so a retry after a lost answer is still the same request.
 */
export function nextAttemptKey(
  current: string,
  decided: boolean,
  make: () => string = newRequestKey,
): string {
  return decided ? make() : current;
}

/** One key per submit attempt: the server treats a repeated key as the same request (no double filing). */
export const newRequestKey = (): string => crypto.randomUUID();
