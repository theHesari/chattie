import { ROLES } from "@/lib/roles";
import type { RoleCardsProps } from "@/types/onboarding";

/** Four role cards as a radio group: keyboard and screen-reader friendly, no extra dependency. */
export function RoleCards({ value, onChange }: RoleCardsProps) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 font-medium text-sm">Role</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {ROLES.map((role) => (
          <label
            className="cursor-pointer"
            htmlFor={`role-${role.id}`}
            key={role.id}
          >
            <input
              checked={value === role.id}
              className="peer sr-only"
              id={`role-${role.id}`}
              name="role"
              onChange={() => onChange(role.id)}
              type="radio"
              value={role.id}
            />
            <span className="flex h-full flex-col gap-1 rounded-lg border border-input p-3 transition-colors hover:bg-muted peer-checked:border-primary peer-checked:bg-muted peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50">
              <span className="font-medium text-sm">{role.label}</span>
              <span className="text-muted-foreground text-xs">
                {role.blurb}
              </span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
