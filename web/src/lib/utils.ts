import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Value of a series at a fractional step, linearly interpolated (null-safe). */
export function at(series: (number | null)[] | undefined, step: number): number {
  if (!series || series.length === 0) return 0;
  const i = Math.floor(step);
  const a = series[clamp(i, 0, series.length - 1)] ?? 0;
  const b = series[clamp(i + 1, 0, series.length - 1)] ?? a;
  return lerp(a, b, step - i);
}

export function decodeB64(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function sum(arrs: ((number | null)[] | undefined)[], i: number): number {
  let s = 0;
  for (const a of arrs) s += (a?.[i] ?? 0);
  return s;
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
