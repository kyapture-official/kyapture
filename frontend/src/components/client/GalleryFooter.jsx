import { ArrowUp } from "lucide-react";

export default function GalleryFooter() {
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <footer className="mt-20 pb-12 px-4">
      <div className="max-w-7xl mx-auto flex flex-col items-center gap-6">
        {/* Back to Top */}
        <button
          onClick={scrollToTop}
          className="group flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-muted hover:text-ink border border-slate-200 hover:border-slate-300 rounded-full px-5 py-2.5 transition-all duration-300 hover:shadow-sm"
        >
          Back to Top
          <ArrowUp className="w-3 h-3 group-hover:-translate-y-0.5 transition-transform duration-300" />
        </button>

        {/* Branding */}
        <p className="text-xs text-muted/60 font-light">
          Powered by{" "}
          <span className="font-serif text-sm text-muted">Kyapture</span>
        </p>
      </div>
    </footer>
  );
}
