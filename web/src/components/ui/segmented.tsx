import { ToggleGroup } from "radix-ui";
import { cn } from "@/lib/utils";

/** Segmented control (Radix ToggleGroup, single). The active pill slides in <120 ms. */
export function Segmented<T extends string>({ value, onChange, options, className, size = "md", label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode; title?: string }[];
  className?: string; size?: "sm" | "md"; label: string;
}) {
  return (
    <ToggleGroup.Root type="single" value={value} aria-label={label}
      onValueChange={(v) => v && onChange(v as T)}
      className={cn("inline-flex shrink-0 rounded-md border bg-background/40 p-0.5", className)}>
      {options.map((o) => (
        <ToggleGroup.Item key={o.value} value={o.value} title={o.title}
          className={cn(
            "whitespace-nowrap rounded-[5px] font-medium text-muted-foreground transition-[background-color,color] duration-100",
            "hover:text-foreground data-[state=on]:bg-raised data-[state=on]:text-foreground",
            "data-[state=on]:shadow-[inset_0_0_0_1px_var(--border)]",
            size === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-8 px-3 text-[13px]",
          )}>
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
