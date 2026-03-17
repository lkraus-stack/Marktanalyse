import { colors, layout } from "@/src/styles/design-tokens";

export type SignalTone = "buy" | "sell" | "hold";

export function signalToneClasses(signal: SignalTone): string {
  if (signal === "buy") {
    return "bg-emerald-500/15 text-emerald-300";
  }
  if (signal === "sell") {
    return "bg-red-500/15 text-red-300";
  }
  return "bg-slate-500/15 text-slate-300";
}

export function sentimentToneClasses(score: number): string {
  if (score > 0.2) {
    return "text-emerald-300";
  }
  if (score < -0.2) {
    return "text-red-300";
  }
  return "text-blue-300";
}

export function ThemeStyles() {
  return (
    <style>{`
      :root {
        --trading-bg-primary: ${colors.bg.primary};
        --trading-bg-card: ${colors.bg.card};
        --trading-bg-card-hover: ${colors.bg.cardHover};
        --trading-border: ${colors.bg.border};
        --trading-text-primary: ${colors.text.primary};
        --trading-text-secondary: ${colors.text.secondary};
        --trading-text-muted: ${colors.text.muted};
        --trading-green: ${colors.accent.green};
        --trading-red: ${colors.accent.red};
        --trading-blue: ${colors.accent.blue};
        --trading-amber: ${colors.accent.amber};
        --trading-header-height: ${layout.headerHeight}px;
        --trading-sidebar-collapsed: ${layout.sidebarCollapsed}px;
        --trading-sidebar-expanded: ${layout.sidebarExpanded}px;
      }

      .trading-surface {
        background: linear-gradient(180deg, rgba(18,18,30,0.98) 0%, rgba(16,16,28,0.98) 100%);
        border: 1px solid rgba(30,30,58,0.66);
        border-radius: 14px;
      }

      .trading-soft-surface {
        background: rgba(18, 18, 30, 0.66);
        border-radius: 12px;
      }

      .trading-hover-glow {
        transition: all 200ms ease;
      }

      .trading-hover-glow:hover {
        background: rgba(26, 26, 46, 0.9);
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3), 0 10px 24px rgba(4, 9, 20, 0.4);
      }

      .trading-noise {
        background-image: radial-gradient(circle at 1px 1px, rgba(148,163,184,0.05) 1px, transparent 0);
        background-size: 18px 18px;
      }

      .trading-scrollbar {
        scrollbar-width: thin;
        scrollbar-color: rgba(100, 116, 139, 0.6) transparent;
      }

      .trading-scrollbar::-webkit-scrollbar {
        width: 10px;
        height: 10px;
      }

      .trading-scrollbar::-webkit-scrollbar-track {
        background: transparent;
      }

      .trading-scrollbar::-webkit-scrollbar-thumb {
        border-radius: 999px;
        background: rgba(100, 116, 139, 0.45);
      }

      .flash-up {
        animation: flashUp 500ms ease-out;
      }

      .flash-down {
        animation: flashDown 500ms ease-out;
      }

      @keyframes flashUp {
        0% { background-color: rgba(34, 197, 94, 0.28); }
        100% { background-color: transparent; }
      }

      @keyframes flashDown {
        0% { background-color: rgba(239, 68, 68, 0.28); }
        100% { background-color: transparent; }
      }
    `}</style>
  );
}
