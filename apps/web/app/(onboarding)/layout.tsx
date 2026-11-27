export default function OnboardingLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      {children}
    </main>
  );
}
