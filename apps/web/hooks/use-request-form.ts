import { useMutation } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useRefreshCompany } from "@/hooks/use-refresh-company";
import { fileRequest, messageFor } from "@/lib/api/company-client";
import {
  buildRequest,
  newRequestKey,
  nextAttemptKey,
  type RequestFormValues,
} from "@/lib/dashboard-format";
import type { RequestKind, RequestResult } from "@/types/company";

export type Decision = { result: RequestResult; startsOn: string };

/**
 * Files a request and keeps its instant decision.
 *
 * One key per attempt: a double click, or a retry after a lost answer, reuses the key and so files one
 * request. The key is replaced only once the server has decided (approved or rejected), so the next
 * attempt is a new request.
 */
export function useRequestForm() {
  const refresh = useRefreshCompany();
  const attempt = useRef(newRequestKey());
  const [decision, setDecision] = useState<Decision | null>(null);

  const mutation = useMutation({
    mutationFn: ({
      kind,
      values,
    }: {
      kind: RequestKind;
      values: RequestFormValues;
    }) => fileRequest(buildRequest(kind, values, attempt.current)),
    onSuccess: (result, { values }) => {
      attempt.current = nextAttemptKey(attempt.current, true);
      setDecision({ result, startsOn: values.startsOn });
      refresh();
    },
  });

  return {
    submit: (kind: RequestKind, values: RequestFormValues) => {
      setDecision(null);
      mutation.mutate({ kind, values });
    },
    decision,
    clearDecision: useCallback(() => setDecision(null), []),
    pending: mutation.isPending,
    error: mutation.error ? messageFor(mutation.error) : null,
  };
}
