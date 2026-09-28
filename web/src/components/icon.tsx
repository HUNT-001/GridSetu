import { SPRITE, type IconName } from "@/icons/sprite.gen";
import { cn } from "@/lib/utils";

/** Mount once: every icon in the app is a <use> into this inline sprite. */
export function IconSprite() {
  return <svg aria-hidden width="0" height="0" style={{ position: "absolute" }}
    dangerouslySetInnerHTML={{ __html: SPRITE }} />;
}

export function Icon({ name, className, title }: { name: IconName; className?: string; title?: string }) {
  return (
    <svg className={cn("size-4 shrink-0", className)} fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true} aria-label={title}>
      <use href={`#i-${name}`} />
    </svg>
  );
}
