"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { layout } from "@/src/styles/design-tokens";

interface AppShellProps {
  children: ReactNode;
}

function getViewportFlags() {
  if (typeof window === "undefined") {
    return { isMobile: false, isDesktop: true };
  }
  const width = window.innerWidth;
  return {
    isMobile: width < 768,
    isDesktop: width >= 1024,
  };
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [viewport, setViewport] = useState(() => getViewportFlags());

  useEffect(() => {
    const handleResize = () => {
      setViewport(getViewportFlags());
      if (window.innerWidth >= 768) {
        setIsMobileSidebarOpen(false);
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const isExpanded = viewport.isDesktop ? isSidebarExpanded : false;
  const sidebarOffset = viewport.isMobile ? 0 : isExpanded ? layout.sidebarExpanded : layout.sidebarCollapsed;

  return (
    <div className="min-h-screen bg-background text-foreground trading-noise">
      <AppSidebar
        isExpanded={isExpanded}
        isMobile={viewport.isMobile}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        onToggleExpanded={() => setIsSidebarExpanded((value) => !value)}
      />
      <AppHeader sidebarOffset={sidebarOffset} onOpenMobileMenu={() => setIsMobileSidebarOpen(true)} />

      <main
        className="min-h-screen transition-all duration-200"
        style={{
          paddingTop: layout.headerHeight,
          paddingLeft: sidebarOffset,
        }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={pathname}
            className="px-4 py-5 md:px-6 md:py-6 xl:px-8"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
