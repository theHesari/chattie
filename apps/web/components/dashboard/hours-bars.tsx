"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHistory } from "@/lib/api/company-client";
import { barHeights, workKindLabel } from "@/lib/dashboard-format";
import { historyKey } from "@/lib/queries/company";
import type { WorkDayKind } from "@/types/company";

const COLOR: Record<WorkDayKind, string> = {
  office: "bg-primary",
  remote: "bg-sky-500",
  leave: "bg-amber-500",
  sick: "bg-rose-400",
  holiday: "bg-muted-foreground/40",
};

export function HoursBars() {
  const { data } = useQuery({ queryKey: historyKey, queryFn: fetchHistory });
  const bars = barHeights(data?.recentWorkDays ?? []);

  return (
    <section aria-labelledby="hours-heading" className="rounded-xl border p-4">
      <h2 className="font-medium text-sm" id="hours-heading">
        Last 30 days
      </h2>
      {bars.length === 0 ? (
        <p className="mt-2 text-muted-foreground text-sm">
          No working days to show yet.
        </p>
      ) : (
        <figure
          aria-label="Hours worked per day"
          className="mt-3 flex h-28 items-end gap-0.5"
        >
          {bars.map((bar) => (
            <div
              aria-label={bar.label}
              className={`min-h-1 flex-1 rounded-sm ${COLOR[bar.kind]}`}
              key={bar.day}
              role="img"
              style={{ height: `${bar.percent}%` }}
              title={bar.label}
            />
          ))}
        </figure>
      )}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground text-xs">
        {(Object.keys(COLOR) as WorkDayKind[]).map((kind) => (
          <li className="flex items-center gap-1.5" key={kind}>
            <span
              aria-hidden="true"
              className={`size-2 rounded-sm ${COLOR[kind]}`}
            />
            {workKindLabel(kind)}
          </li>
        ))}
      </ul>
    </section>
  );
}
