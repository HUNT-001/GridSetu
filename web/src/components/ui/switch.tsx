import { Switch as S } from "radix-ui";
import { cn } from "@/lib/utils";

export function Switch({ checked, onChange, label, className }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; className?: string;
}) {
  return (
    <S.Root checked={checked} onCheckedChange={onChange} aria-label={label}
      className={cn("relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent",
        "bg-raised transition-colors duration-100 data-[state=checked]:bg-primary", className)}>
      <S.Thumb className="block size-4 translate-x-0.5 rounded-full bg-foreground shadow transition-transform duration-100 data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-primary-foreground" />
    </S.Root>
  );
}
