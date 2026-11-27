"use client";

import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useLayoutEffect, useState } from "react";
import { toneClass } from "@/components/dashboard/tone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useRequestForm } from "@/hooks/use-request-form";
import { useUndoRequest } from "@/hooks/use-undo-request";
import { fetchHistory } from "@/lib/api/company-client";
import {
  canUndo,
  fieldsFor,
  kindLabel,
  REQUEST_KINDS,
  statusTone,
} from "@/lib/dashboard-format";
import { historyKey } from "@/lib/queries/company";
import type { RequestKind } from "@/types/company";

const field = (form: FormData, name: string) => String(form.get(name) ?? "");

export function RequestForm() {
  const { data } = useQuery({ queryKey: historyKey, queryFn: fetchHistory });
  const today = data?.today ?? "";
  const { submit, decision, clearDecision, pending, error } = useRequestForm();
  const undoer = useUndoRequest();
  const [kind, setKind] = useState<RequestKind>("day_off");
  const fields = fieldsFor(kind);
  const resetUndo = undoer.reset;

  // Next keeps a visited page alive (hidden) and brings it back with its state: drop a stale answer when hidden.
  useLayoutEffect(
    () => () => {
      clearDecision();
      resetUndo();
    },
    [clearDecision, resetUndo],
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetUndo(); // an earlier "Cancelled by you" must not hide this request's answer
    const form = new FormData(event.currentTarget);
    submit(kind, {
      startsOn: field(form, "startsOn"),
      endsOn: field(form, "endsOn"),
      startTime: field(form, "startTime"),
      endTime: field(form, "endTime"),
      hours: field(form, "hours"),
      reason: field(form, "reason"),
    });
  };

  const shown = undoer.result ?? decision?.result ?? null;
  const undoable =
    decision?.result.id != null &&
    !undoer.result &&
    canUndo(
      { status: decision.result.status, startsOn: decision.startsOn },
      today,
    );

  return (
    <section
      aria-labelledby="request-heading"
      className="rounded-xl border p-4"
    >
      <h2 className="font-medium text-sm" id="request-heading">
        File a request
      </h2>
      <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kind">Type</Label>
          <NativeSelect
            id="kind"
            onChange={(event) => {
              setKind(event.target.value as RequestKind);
              clearDecision();
              resetUndo();
            }}
            value={kind}
          >
            {REQUEST_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="startsOn">{fields.endDate ? "From" : "Date"}</Label>
          <Input
            defaultValue={today}
            id="startsOn"
            name="startsOn"
            required
            type="date"
          />
        </div>
        {fields.endDate && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="endsOn">To (optional)</Label>
            <Input id="endsOn" name="endsOn" type="date" />
          </div>
        )}
        {fields.times && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="startTime">Start time</Label>
              <Input id="startTime" name="startTime" required type="time" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="endTime">End time</Label>
              <Input id="endTime" name="endTime" required type="time" />
            </div>
          </>
        )}
        {fields.hours && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hours">Hours</Label>
            <Input
              id="hours"
              max={24}
              min={0.25}
              name="hours"
              required
              step={0.25}
              type="number"
            />
          </div>
        )}
        {fields.reason && (
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="reason">Reason (optional)</Label>
            <Input id="reason" maxLength={500} name="reason" />
          </div>
        )}
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button disabled={pending} type="submit">
            {pending ? "Deciding…" : "Submit"}
          </Button>
          <p className="text-muted-foreground text-xs">
            You get the answer right away.
          </p>
        </div>
      </form>

      <div
        aria-live="polite"
        className="mt-3 flex min-h-6 flex-wrap items-center gap-3 text-sm"
      >
        {shown && (
          <p className={toneClass[statusTone(shown.status)]}>
            {shown.decisionReason}
            {shown.balanceAfter !== null && shown.status === "approved"
              ? ` · ${shown.balanceAfter} days left`
              : ""}
          </p>
        )}
        {undoable && decision?.result.id != null && (
          <Button
            disabled={undoer.undoing}
            onClick={() => undoer.undo(decision.result.id as number)}
            size="sm"
            type="button"
            variant="outline"
          >
            {undoer.undoing ? "Undoing…" : "Undo"}
          </Button>
        )}
        {(error ?? undoer.error) && (
          <p className="text-destructive">{error ?? undoer.error}</p>
        )}
      </div>
    </section>
  );
}
