"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchTeam } from "@/lib/api/company-client";
import { formatDateRange, workKindLabel } from "@/lib/dashboard-format";
import { teamKey } from "@/lib/queries/company";

export function TeamTable() {
  const { data: team } = useQuery({ queryKey: teamKey, queryFn: fetchTeam });

  return (
    <section aria-labelledby="team-heading" className="rounded-xl border p-4">
      <h2 className="font-medium text-sm" id="team-heading">
        Your team
      </h2>
      {team && team.length === 0 && (
        <p className="mt-2 text-muted-foreground text-sm">No direct reports.</p>
      )}
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground text-xs">
            <tr>
              <th className="py-1 pr-3 font-medium" scope="col">
                Name
              </th>
              <th className="py-1 pr-3 font-medium" scope="col">
                Role
              </th>
              <th className="py-1 pr-3 font-medium" scope="col">
                Today
              </th>
              <th className="py-1 font-medium" scope="col">
                Next away
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {(team ?? []).map((member) => (
              <tr key={member.id}>
                <td className="py-1.5 pr-3" dir="auto">
                  {member.name}
                </td>
                <td className="py-1.5 pr-3 text-muted-foreground">
                  {member.title}
                </td>
                <td className="py-1.5 pr-3">
                  {member.todayStatus ? workKindLabel(member.todayStatus) : "—"}
                </td>
                <td className="py-1.5">
                  {member.nextAway
                    ? formatDateRange(member.nextAway, member.nextAway)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
