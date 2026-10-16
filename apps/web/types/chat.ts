import type { ChatStatus, DynamicToolUIPart, UIMessage } from "ai";
import type { ReactNode } from "react";

export type { ChatStatus, UIMessage };

/** Tools are streamed as dynamic tools, so the UI needs no per-tool type definitions. */
export type ToolPart = DynamicToolUIPart;
export type ToolStatus = "running" | "done" | "error";

/** Props Next.js passes to an `error.tsx` boundary. */
export type RouteErrorProps = {
  error: unknown;
  retry: () => void;
};

export type ChatThreadProps = {
  params: Promise<{ id: string }>;
};

export type ChatProps = {
  id: string;
  initialMessages: UIMessage[];
};

export type ChatMessageProps = {
  message: UIMessage;
  isStreaming: boolean;
};

export type ConversationProps = {
  children: ReactNode;
};

export type ToolCardProps = {
  part: ToolPart;
};

export type ToolSectionProps = {
  title: string;
  value: unknown;
};

export type PromptFormProps = {
  isBusy: boolean;
  onSubmit: (text: string) => void;
  onStop: () => void;
};

export type SuggestionsProps = {
  suggestions: readonly string[];
  onSelect: (suggestion: string) => void;
};
