import { type KeyboardEvent, useState } from "react";

/** Controlled textarea state: Enter submits, Shift+Enter inserts a newline. */
export function usePromptInput(onSubmit: (text: string) => void) {
  const [value, setValue] = useState("");

  const submit = () => {
    if (!value.trim()) return;
    onSubmit(value);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (event.nativeEvent.isComposing) return; // IME input (e.g. Persian, CJK) in progress
    event.preventDefault();
    submit();
  };

  return { value, setValue, submit, onKeyDown };
}
