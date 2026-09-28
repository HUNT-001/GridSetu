import * as React from "react";
import { Tabs as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export function TabsList({ className, ...p }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn("inline-flex gap-1 border-b", className)} {...p} />;
}
export function TabsTrigger({ className, ...p }: React.ComponentProps<typeof T.Trigger>) {
  return <T.Trigger className={cn(
    "-mb-px border-b-2 border-transparent px-2.5 pb-2 pt-1 text-[13px] font-medium text-muted-foreground",
    "transition-colors duration-100 hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground",
    className)} {...p} />;
}
export function TabsContent({ className, ...p }: React.ComponentProps<typeof T.Content>) {
  return <T.Content className={cn("pt-3 data-[state=active]:animate-in", className)} {...p} />;
}
