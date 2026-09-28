import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Icon } from "@/components/icon";
import { cn } from "@/lib/utils";

export interface Column<R> {
  key: string;
  header: string;
  width: string;                         // CSS grid track, e.g. "90px" or "1fr"
  align?: "left" | "right";
  value: (r: R) => number | string;      // used for sorting and search
  cell?: (r: R) => React.ReactNode;
  mono?: boolean;
}

/** Virtualised, sortable, searchable table: only the visible rows are in the DOM, so
 *  thousands of rows scroll at 60 fps. Uses its own scroll box (Lenis steps aside). */
export function DataTable<R>({ rows, columns, height = 460, rowHeight = 36, search, initialSort,
  empty = "No rows match this filter.", onRowClick, label, minWidth = 720 }: {
  rows: R[]; columns: Column<R>[]; height?: number; rowHeight?: number; search?: string; minWidth?: number;
  initialSort?: { key: string; dir: 1 | -1 }; empty?: string; onRowClick?: (r: R) => void; label: string;
}) {
  const [sort, setSort] = useState(initialSort ?? { key: columns[0].key, dir: 1 as 1 | -1 });
  const box = useRef<HTMLDivElement>(null);
  const tracks = columns.map((c) => c.width).join(" ");
  const view = useMemo(() => {
    const col = columns.find((c) => c.key === sort.key) ?? columns[0];
    const q = search?.trim().toLowerCase();
    const filtered = q
      ? rows.filter((r) => columns.some((c) => String(c.value(r)).toLowerCase().includes(q)))
      : rows.slice();
    filtered.sort((a, b) => {
      const va = col.value(a), vb = col.value(b);
      return (typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb))) * sort.dir;
    });
    return filtered;
  }, [rows, columns, sort, search]);

  const v = useVirtualizer({ count: view.length, getScrollElement: () => box.current,
    estimateSize: () => rowHeight, overscan: 12 });

  return (
    <div className="overflow-hidden rounded-lg border" role="table" aria-label={label} aria-rowcount={view.length}>
     <div className="overflow-x-auto" data-lenis-prevent>
     <div style={{ minWidth }}>
      <div className="grid border-b bg-raised/60 text-[12px] font-medium text-muted-foreground" style={{ gridTemplateColumns: tracks }} role="row">
        {columns.map((c) => (
          <button key={c.key} role="columnheader" type="button"
            aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
            onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (-s.dir as 1 | -1) : 1 }))}
            className={cn("flex h-9 items-center gap-1 whitespace-nowrap px-3 transition-colors duration-100 hover:text-foreground",
              c.align === "right" && "justify-end")}>
            {c.header}
            <Icon name={sort.key === c.key ? (sort.dir === 1 ? "arrow-up" : "arrow-down") : "arrow-up-down"}
              className={cn("size-3", sort.key !== c.key && "opacity-40")} />
          </button>
        ))}
      </div>
      <div ref={box} data-lenis-prevent className="overflow-auto overscroll-contain" style={{ height }}>
        {view.length === 0 ? (
          <div className="grid h-full place-items-center text-[13px] text-muted-foreground">{empty}</div>
        ) : (
          <div style={{ height: v.getTotalSize(), position: "relative" }}>
            {v.getVirtualItems().map((vi) => {
              const r = view[vi.index];
              return (
                <div key={vi.key} role="row" onClick={onRowClick ? () => onRowClick(r) : undefined}
                  className={cn("absolute left-0 right-0 grid items-center border-b border-border/60 text-[13px]",
                    "transition-colors duration-100 hover:bg-raised/50", onRowClick && "cursor-pointer")}
                  style={{ gridTemplateColumns: tracks, height: rowHeight, transform: `translateY(${vi.start}px)` }}>
                  {columns.map((c) => (
                    <div key={c.key} role="cell"
                      className={cn("truncate px-3", c.align === "right" && "text-right", c.mono && "num")}>
                      {c.cell ? c.cell(r) : c.value(r)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
     </div>
     </div>
      <div className="border-t px-3 py-1.5 text-[12px] text-muted-foreground">
        <span className="num">{view.length.toLocaleString("en-IN")}</span> of <span className="num">{rows.length.toLocaleString("en-IN")}</span> rows
      </div>
    </div>
  );
}
