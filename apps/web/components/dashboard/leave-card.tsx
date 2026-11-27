"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHistory } from "@/lib/api/company-client";
import { historyKey } from "@/lib/queries/company";

export function LeaveCard() {
  const { data } = useQuery({ queryKey: historyKey, queryFn: fetchHistory });
  const balance = data?.balance;
  const usedPercent =
    balance && balance.allowance > 0
      ? Math.min(100, Math.round((balance.used / balance.allowance) * 100))
      : 0;

  return (
    <section aria-labelledby="leave-heading" className="rounded-xl border p-4">
      <h2 className="font-medium text-sm" id="leave-heading">
        Leave {balance ? `in ${balance.year}` : ""}
      </h2>
      {balance ? (
        <>
          <p className="mt-2 font-semibold text-3xl">
            {balance.remaining}
            <span className="ml-1.5 font-normal text-muted-foreground text-sm">
              of {balance.allowance} days left
            </span>
          </p>
          <div
            aria-label={`${balance.used} of ${balance.allowance} days used`}
            className="mt-3 h-2 overflow-hidden rounded-full bg-muted"
            role="img"
          >
            <div
              className="h-full bg-primary"
              style={{ width: `${usedPercent}%` }}
            />
          </div>
          <p className="mt-2 text-muted-foreground text-xs">
            {balance.used} used so far this year
          </p>
        </>
      ) : (
        <p className="mt-2 text-muted-foreground text-sm">Loading…</p>
      )}
    </section>
  );
}
