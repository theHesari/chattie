"use client";

import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { usePromptInput } from "@/hooks/use-prompt-input";
import type { PromptFormProps } from "@/types/chat";

export function PromptForm({ isBusy, onSubmit, onStop }: PromptFormProps) {
  const { value, setValue, submit, onKeyDown } = usePromptInput(onSubmit);

  return (
    <form
      className="flex items-end gap-2 rounded-xl border bg-background p-2 focus-within:ring-2 focus-within:ring-ring/50"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Textarea
        aria-label="Message"
        className="max-h-48 min-h-10 resize-none border-0 shadow-none focus-visible:ring-0"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Message Chattie…"
        rows={1}
        value={value}
      />
      {isBusy ? (
        <Button aria-label="Stop" onClick={onStop} size="icon" type="button">
          <SquareIcon />
        </Button>
      ) : (
        <Button
          aria-label="Send"
          disabled={!value.trim()}
          size="icon"
          type="submit"
        >
          <ArrowUpIcon />
        </Button>
      )}
    </form>
  );
}
