/** The characters a user can play, and the departments they can join. Pure: no imports at runtime. */
import type { Role } from "@/types/company";

export type RoleOption = {
  id: Role;
  label: string;
  /** What this role can see, in one line; it mirrors the row-level security rules in the database. */
  blurb: string;
  needsDepartment: boolean;
};

export const ROLES: readonly RoleOption[] = [
  {
    id: "employee",
    label: "Employee",
    blurb: "Your own history, requests and orders, plus the company directory.",
    needsDepartment: true,
  },
  {
    id: "manager",
    label: "Manager",
    blurb: "Your own data plus your team's requests, hours and orders.",
    needsDepartment: true,
  },
  {
    id: "hr",
    label: "HR",
    blurb: "Everyone's requests, hours and salaries; orders only your own.",
    needsDepartment: false,
  },
  {
    id: "admin",
    label: "Admin",
    blurb: "The whole company: people, salaries, customers and orders.",
    needsDepartment: false,
  },
];

/** Ids are the department ids the API validates (services/llm/company/characters.py). */
export const DEPARTMENTS: readonly { id: number; name: string }[] = [
  { id: 2, name: "Sales" },
  { id: 3, name: "Engineering" },
  { id: 4, name: "Marketing" },
  { id: 6, name: "Customer Support" },
];

/** The department id to send for a role: only roles that take one, and only a known id. */
export function departmentFor(role: Role, chosen: number): number | null {
  const option = ROLES.find((r) => r.id === role);
  if (!option?.needsDepartment) return null;
  return DEPARTMENTS.some((d) => d.id === chosen) ? chosen : null;
}
