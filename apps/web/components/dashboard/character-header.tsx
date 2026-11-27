import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ROLES } from "@/lib/roles";
import { CHANGE_CHARACTER_PATH } from "@/lib/routes";
import type { CharacterHeaderProps } from "@/types/dashboard";

export function CharacterHeader({ character }: CharacterHeaderProps) {
  const role =
    ROLES.find((r) => r.id === character.role)?.label ?? character.role;

  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate font-semibold text-xl" dir="auto">
          {character.name}
        </h1>
        <p className="text-muted-foreground text-sm">
          {character.title} · {character.department} · {role}
          {character.managerName
            ? ` · reports to ${character.managerName}`
            : ""}
        </p>
      </div>
      <Button asChild size="sm" variant="outline">
        <Link href={CHANGE_CHARACTER_PATH}>Switch character</Link>
      </Button>
    </header>
  );
}
