"use client";

import { useQuery } from "@tanstack/react-query";
import { toneClass } from "@/components/dashboard/tone";
import { Button } from "@/components/ui/button";
import { useUndoRequest } from "@/hooks/use-undo-request";
import { fetchHistory, fetchRequests } from "@/lib/api/company-client";
import {
  canUndo,
  formatDateRange,
  kindLabel,
  statusTone,
} from "@/lib/dashboard-format";
import { historyKey, requestsKey } from "@/lib/queries/company";

export function RequestList() {
  const { data: requests } = useQuery({
    queryKey: requestsKey,
    queryFn: fetchRequests,
  });
  const { data: history } = useQuery({
    queryKey: historyKey,
    queryFn: fetchHistory,
  });
  const { undo, undoing, error } = useUndoRequest();
  const today = history?.today ?? "";

  return (
    <section
      aria-labelledby="requests-heading"
      className="rounded-xl border p-4"
    >
      <h2 className="font-medium text-sm" id="requests-heading">
        Your requests
      </h2>
      {error && (
        <p className="mt-2 text-destructive text-sm" role="alert">
          {error}
        </p>
      )}
      {requests && requests.length === 0 && (
        <p className="mt-2 text-muted-foreground text-sm">No requests yet.</p>
      )}
      <ul className="mt-2 divide-y">
        {(requests ?? []).slice(0, 15).map((request) => (
          <li
            className="flex items-start justify-between gap-3 py-2"
            key={request.id}
          >
            <div className="min-w-0">
              <p className="text-sm">
                <span className="font-medium">{kindLabel(request.kind)}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · {formatDateRange(request.startsOn, request.endsOn)}
                </span>
              </p>
              <p
                className={`truncate text-xs ${toneClass[statusTone(request.status)]}`}
                title={request.decisionReason}
              >
                {request.decisionReason}
              </p>
            </div>
            {canUndo(request, today) && (
              <Button
                disabled={undoing}
                onClick={() => undo(request.id)}
                size="xs"
                type="button"
                variant="outline"
              >
                Undo
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
