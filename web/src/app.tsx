import { useEffect, useRef } from "react";
import { Route, Router, Switch, useLocation } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { IS_DEMO } from "@/lib/api";
import Lenis from "lenis";
import gsap from "gsap";
import { IconSprite } from "@/components/icon";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MobileNav, Sidebar, Topbar } from "@/components/layout/shell";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/icon";
import { useActiveRun, useFeeder, usePrefetchRun, useRuns } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { prefersReducedMotion } from "@/lib/utils";
import Overview from "@/pages/overview";
import CityPage from "@/pages/city";
import FeederPage from "@/pages/feeder";
import HouseholdsPage from "@/pages/households";
import WamsPage from "@/pages/wams";
import ArchitecturePage from "@/pages/architecture";
import LabPage from "@/pages/lab";

/** Lenis smooth scrolling driven by the GSAP ticker (one clock for scroll and tweens). */
function useSmoothScroll() {
  const lenis = useRef<Lenis | null>(null);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const l = new Lenis({ lerp: 0.14, wheelMultiplier: 1, smoothWheel: true, autoRaf: false });
    lenis.current = l;
    const tick = (t: number) => l.raf(t * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => { gsap.ticker.remove(tick); l.destroy(); lenis.current = null; };
  }, []);
  return lenis;
}

// The shared single-file copy lives at an arbitrary URL, so it routes in memory.
const demoLocation = IS_DEMO ? memoryLocation({ path: "/" }) : null;

export default function App() {
  return demoLocation ? <Router hook={demoLocation.hook}><Shell /></Router> : <Shell />;
}

function Shell() {
  const lenis = useSmoothScroll();
  const [loc] = useLocation();
  usePrefetchRun();
  const { data: f } = useFeeder();
  useEffect(() => { if (f) useUI.getState().setNSteps(f.n); }, [f]);
  useEffect(() => {
    if (lenis.current) lenis.current.scrollTo(0, { immediate: true });
    else window.scrollTo(0, 0);
  }, [loc, lenis]);

  return (
    <TooltipProvider>
      <IconSprite />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-panel focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main id="main" className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-4 md:px-6">
            <Gate>
              <div key={loc} className="animate-in">
                <Switch>
                  <Route path="/" component={Overview} />
                  <Route path="/city" component={CityPage} />
                  <Route path="/feeder" component={FeederPage} />
                  <Route path="/households" component={HouseholdsPage} />
                  <Route path="/wams" component={WamsPage} />
                  <Route path="/architecture" component={ArchitecturePage} />
                  <Route path="/lab" component={LabPage} />
                  <Route><NotFound /></Route>
                </Switch>
              </div>
            </Gate>
          </main>
          <MobileNav />
        </div>
      </div>
    </TooltipProvider>
  );
}

/** Explains the one state where there is nothing to show yet: the first run is computing
 *  or the API is unreachable. Everything else renders skeletons in place. */
function Gate({ children }: { children: React.ReactNode }) {
  const runs = useRuns();
  const { run } = useActiveRun();
  if (runs.isError) {
    return (
      <div className="mx-auto mt-16 max-w-lg rounded-xl border bg-panel p-6">
        <h2 className="font-display text-[28px] leading-tight">The GridSetu API is not reachable</h2>
        <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
          Start it from the project folder with <code className="num rounded bg-raised px-1.5 py-0.5">gridsetu serve</code>,
          then retry. The dashboard expects it on port 8000.
        </p>
        <Button className="mt-4" onClick={() => runs.refetch()}><Icon name="refresh-cw" />Retry</Button>
      </div>
    );
  }
  if (run && run.status !== "ready" && !useUI.getState().runId) {
    return (
      <div className="mx-auto mt-16 max-w-lg rounded-xl border bg-panel p-6" role="status">
        <h2 className="font-display text-[28px] leading-tight">Simulating the reference week</h2>
        <p className="mt-2 text-[13.5px] text-muted-foreground">{run.message}</p>
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-raised">
          <div className="h-full rounded-full bg-primary transition-[width] duration-150" style={{ width: `${run.progress * 100}%` }} />
        </div>
        <p className="mt-3 text-[12.5px] text-faint">This happens once. Results are cached, so the next start is instant.</p>
      </div>
    );
  }
  return <>{children}</>;
}

function NotFound() {
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <h2 className="font-display text-[30px]">Nothing on this page</h2>
      <p className="mt-2 text-[13.5px] text-muted-foreground">Pick a page from the menu on the left.</p>
    </div>
  );
}
