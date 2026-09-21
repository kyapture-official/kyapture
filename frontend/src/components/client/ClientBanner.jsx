import { useState } from "react";
import { X, Users } from "lucide-react";

export default function ClientBanner({ clientName }) {
  const [visible, setVisible] = useState(true);

  if (!visible || !clientName) return null;

  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 animate-fade-up">
      <div className="flex items-center gap-2.5 bg-white/90 backdrop-blur-md border border-slate-200/60 rounded-full px-4 py-2 shadow-lg">
        <Users className="w-3.5 h-3.5 text-muted" />
        <span className="text-xs text-muted font-light tracking-wide">
          Viewing collection as{" "}
          <span className="font-medium text-ink">{clientName}</span>
        </span>
        <button
          onClick={() => setVisible(false)}
          className="ml-1 p-0.5 rounded-full hover:bg-slate-100 text-muted transition-colors"
          aria-label="Dismiss banner"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
