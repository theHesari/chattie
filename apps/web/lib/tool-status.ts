import type { ToolPart, ToolStatus } from "@/types/chat";

export function toolStatus(state: ToolPart["state"]): ToolStatus {
  switch (state) {
    case "output-available":
      return "done";
    case "output-error":
    case "output-denied":
      return "error";
    default:
      return "running";
  }
}
