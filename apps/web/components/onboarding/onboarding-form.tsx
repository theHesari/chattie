"use client";

import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { RoleCards } from "@/components/onboarding/role-cards";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useOnboarding } from "@/hooks/use-onboarding";
import { DEPARTMENTS, departmentFor, ROLES } from "@/lib/roles";
import type { Role } from "@/types/company";
import type { OnboardingFormProps } from "@/types/onboarding";

export function OnboardingForm({
  replacing,
  defaultName,
}: OnboardingFormProps) {
  const { submit, error, pending, succeeded, reset } = useOnboarding();
  const [role, setRole] = useState<Role>("employee");
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const confirmed = !replacing || replaceConfirmed;
  const formRef = useRef<HTMLFormElement>(null);
  const finished = useRef(false);
  const needsDepartment = ROLES.find((r) => r.id === role)?.needsDepartment;

  // Next hides a page you leave instead of discarding it, and shows it again with its old state. After a
  // successful submit that would bring this form back stuck on "Creating your character…", so once it is
  // hidden we start it over. An abandoned draft is kept.
  useEffect(() => {
    if (succeeded) finished.current = true;
  }, [succeeded]);
  useLayoutEffect(
    () => () => {
      if (!finished.current) return;
      finished.current = false;
      reset();
      setRole("employee");
      setReplaceConfirmed(false);
      formRef.current?.reset();
    },
    [reset],
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    submit({
      displayName: String(form.get("displayName") ?? "").trim(),
      role,
      departmentId: departmentFor(role, Number(form.get("departmentId"))),
    });
  };

  return (
    <form
      className="flex w-full max-w-xl flex-col gap-5"
      onSubmit={onSubmit}
      ref={formRef}
    >
      <div>
        <h1 className="font-semibold text-xl">
          {replacing ? "Switch character" : "Create your character"}
        </h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Choose who you are at the company. The assistant answers according to
          what that role is allowed to see.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="displayName">Display name</Label>
        <Input
          autoComplete="name"
          defaultValue={defaultName}
          id="displayName"
          name="displayName"
          required
        />
      </div>

      <RoleCards onChange={setRole} value={role} />

      {needsDepartment && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="departmentId">Department</Label>
          <NativeSelect
            defaultValue={DEPARTMENTS[0].id}
            id="departmentId"
            name="departmentId"
          >
            {DEPARTMENTS.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      {replacing ? (
        <label
          className="flex items-start gap-2 text-sm"
          htmlFor="confirm-replace"
        >
          <input
            checked={replaceConfirmed}
            className="mt-0.5"
            id="confirm-replace"
            onChange={(event) => setReplaceConfirmed(event.target.checked)}
            type="checkbox"
          />
          <span>
            I understand that my current character and its history will be
            replaced by a new one.
          </span>
        </label>
      ) : (
        <p className="text-muted-foreground text-xs">
          You can switch character later, but that starts a new history.
        </p>
      )}

      <div aria-live="polite">
        {error && <p className="text-destructive text-sm">{error}</p>}
      </div>

      <Button disabled={pending || !confirmed} type="submit">
        {pending ? "Creating your character…" : "Start"}
      </Button>
    </form>
  );
}
