import { SignOutButton } from "@/components/sidebar/sign-out-button";
import { requireUser } from "@/lib/session";

/** Signed-in user's email and a sign-out button (reads the session: render inside <Suspense>). */
export async function UserMenu() {
  const user = await requireUser();

  return (
    <div className="flex items-center justify-between gap-2 px-1">
      <span
        className="truncate text-muted-foreground text-sm"
        title={user.email}
      >
        {user.email}
      </span>
      <SignOutButton />
    </div>
  );
}
