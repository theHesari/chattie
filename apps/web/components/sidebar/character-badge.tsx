import { getMe } from "@/lib/api/company";
import { ApiUnavailableError } from "@/lib/api/shared";
import { ROLES } from "@/lib/roles";

/** Who the signed-in user is at the company: name, title and role (reads the session: render inside <Suspense>). */
export async function CharacterBadge() {
  try {
    const character = await getMe();
    if (!character) return null;
    const role =
      ROLES.find((r) => r.id === character.role)?.label ?? character.role;

    return (
      <div className="px-1 pb-2">
        <p
          className="truncate font-medium text-sm"
          dir="auto"
          title={character.name}
        >
          {character.name}
        </p>
        <p
          className="truncate text-muted-foreground text-xs"
          title={`${character.title} · ${role}`}
        >
          {character.title} · {role}
        </p>
      </div>
    );
  } catch (error) {
    // The API being down is expected: the sidebar just goes without the badge.
    if (error instanceof ApiUnavailableError) return null;
    throw error;
  }
}
