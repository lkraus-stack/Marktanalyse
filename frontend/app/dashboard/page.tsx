"use client";

import { useEffect, useState } from "react";

import DashboardView from "@/app/dashboard/dashboard-view";

export default function DashboardPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <p className="text-muted-foreground">Laden...</p>
      </div>
    );
  }
  return <DashboardView />;
}
