import type { Role } from "@/types/company";

export type OnboardingFormProps = {
  /** A character already exists: creating a new one replaces it and its history. */
  replacing: boolean;
  /** Suggested display name (the account's name). */
  defaultName: string;
};

export type RoleCardsProps = {
  value: Role;
  onChange: (role: Role) => void;
};
