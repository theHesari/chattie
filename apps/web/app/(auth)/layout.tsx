import { Suspense } from "react";
import { RedirectIfSignedIn } from "@/components/auth/redirect-if-signed-in";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      {/* A real session check (the proxy only sees whether a cookie exists). */}
      <Suspense>
        <RedirectIfSignedIn />
      </Suspense>
      {children}
    </main>
  );
}
