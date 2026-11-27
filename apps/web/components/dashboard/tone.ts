import type { Tone } from "@/types/dashboard";

/** Text colour for a decision: green for approved, red for rejected, grey for cancelled. */
export const toneClass: Record<Tone, string> = {
  good: "text-emerald-700 dark:text-emerald-400",
  bad: "text-destructive",
  muted: "text-muted-foreground",
};
