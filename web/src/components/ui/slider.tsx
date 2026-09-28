import { Slider as S } from "radix-ui";
import { cn } from "@/lib/utils";

export function Slider({ value, onChange, min, max, step, className, label }: {
  value: number; onChange: (v: number) => void; min: number; max: number; step: number; className?: string;
  label: string;
}) {
  return (
    <S.Root value={[value]} min={min} max={max} step={step} onValueChange={([v]) => onChange(v)}
      className={cn("relative flex h-5 w-full touch-none select-none items-center", className)}>
      <S.Track className="relative h-1 grow overflow-hidden rounded-full bg-raised">
        <S.Range className="absolute h-full bg-primary" />
      </S.Track>
      <S.Thumb aria-label={label} className="block size-4 rounded-full border-2 border-primary bg-panel shadow transition-transform duration-100 hover:scale-110 focus-visible:scale-110" />
    </S.Root>
  );
}
