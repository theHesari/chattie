"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHistory } from "@/lib/api/company-client";
import { formatDateRange } from "@/lib/dashboard-format";
import { historyKey } from "@/lib/queries/company";

export function Timeline() {
  const { data } = useQuery({ queryKey: historyKey, queryFn: fetchHistory });
  const events = (data?.events ?? []).slice(0, 12);

  return (
    <section
      aria-labelledby="timeline-heading"
      className="rounded-xl border p-4"
    >
      <h2 className="font-medium text-sm" id="timeline-heading">
        Timeline
      </h2>
      <ol className="mt-2 divide-y">
        {events.map((event, index) => {
          const day = event.happenedAt.slice(0, 10);
          return (
            <li
              className="flex items-baseline justify-between gap-3 py-1.5 text-sm"
              key={`${index}-${event.happenedAt}-${event.title}`}
            >
              <span>{event.title}</span>
              <span className="shrink-0 text-muted-foreground text-xs">
                {formatDateRange(day, day)}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
