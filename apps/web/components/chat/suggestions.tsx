import { Button } from "@/components/ui/button";
import type { SuggestionsProps } from "@/types/chat";

export function Suggestions({ suggestions, onSelect }: SuggestionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((suggestion) => (
        <Button
          className="rounded-full"
          key={suggestion}
          onClick={() => onSelect(suggestion)}
          size="sm"
          type="button"
          variant="outline"
        >
          {suggestion}
        </Button>
      ))}
    </div>
  );
}
