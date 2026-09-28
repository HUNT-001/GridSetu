import * as React from "react";
import { Dialog as D } from "radix-ui";
import { Icon } from "@/components/icon";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;

export function DialogContent({ title, description, children, className }: {
  title: string; description?: string; children: React.ReactNode; className?: string;
}) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-[#020a14]/60 backdrop-blur-[2px] data-[state=open]:animate-[fade-in_120ms_var(--ease-snap)]" />
      <D.Content className={cn(
        "fixed left-1/2 top-1/2 z-50 w-[min(92vw,560px)] -translate-x-1/2 -translate-y-1/2",
        "rounded-xl border bg-panel p-5 shadow-2xl data-[state=open]:animate-[fade-in_140ms_var(--ease-snap)]",
        className)}>
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <D.Title className="font-display text-[26px] leading-tight">{title}</D.Title>
            {description && <D.Description className="mt-1 text-[13px] text-muted-foreground">{description}</D.Description>}
          </div>
          <D.Close className="rounded-md p-1.5 text-muted-foreground transition-colors duration-100 hover:bg-raised hover:text-foreground" aria-label="Close">
            <Icon name="x" />
          </D.Close>
        </div>
        {children}
      </D.Content>
    </D.Portal>
  );
}
