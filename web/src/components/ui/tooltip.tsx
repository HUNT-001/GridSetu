import * as React from "react";
import { Tooltip as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const TooltipProvider = ({ children }: { children: React.ReactNode }) => (
  <T.Provider delayDuration={250} skipDelayDuration={100}>{children}</T.Provider>
);

export function Tooltip({ content, children, side = "top" }: {
  content: React.ReactNode; children: React.ReactNode; side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6}
          className={cn("z-50 max-w-72 rounded-md border bg-raised px-2.5 py-1.5 text-[12.5px] leading-snug",
            "text-foreground shadow-lg data-[state=delayed-open]:animate-in")}>
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
