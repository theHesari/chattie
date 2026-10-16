import {
  CheckCircleIcon,
  ChevronDownIcon,
  LoaderIcon,
  WrenchIcon,
  XCircleIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { toolStatus } from "@/lib/tool-status";
import type { ToolCardProps, ToolSectionProps, ToolStatus } from "@/types/chat";

const STATUS_BADGE: Record<ToolStatus, { label: string; icon: ReactNode }> = {
  running: {
    label: "Running",
    icon: <LoaderIcon className="size-3.5 animate-spin" />,
  },
  done: {
    label: "Completed",
    icon: <CheckCircleIcon className="size-3.5 text-green-600" />,
  },
  error: {
    label: "Error",
    icon: <XCircleIcon className="size-3.5 text-destructive" />,
  },
};

/** Collapsible card showing one tool call: name, status, input and result. */
export function ToolCard({ part }: ToolCardProps) {
  const badge = STATUS_BADGE[toolStatus(part.state)];

  return (
    <Collapsible className="w-full rounded-lg border">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 p-3 text-sm">
        <WrenchIcon className="size-4 text-muted-foreground" />
        <span className="font-medium">{part.toolName}</span>
        <span className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs">
          {badge.icon}
          {badge.label}
        </span>
        <ChevronDownIcon className="ml-auto size-4 transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 border-t p-3">
        <ToolSection title="Input" value={part.input} />
        {part.state === "output-available" && (
          <ToolSection title="Result" value={part.output} />
        )}
        {part.state === "output-error" && (
          <ToolSection title="Error" value={part.errorText} />
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function ToolSection({ title, value }: ToolSectionProps) {
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);

  return (
    <section className="space-y-1">
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {title}
      </h4>
      <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-muted p-2 text-xs">
        {text}
      </pre>
    </section>
  );
}
