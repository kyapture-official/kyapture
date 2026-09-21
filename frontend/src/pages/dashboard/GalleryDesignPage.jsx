import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import CoverPreview from "../../components/shared/CoverPreview";
import { useToast } from "../../components/ui/Toast";

const COVER_LAYOUTS = [
  { id: "center", label: "Center", desc: "Centered text overlay" },
  { id: "left", label: "Left", desc: "Left-aligned text" },
  { id: "novel", label: "Novel", desc: "Corner flourishes" },
  { id: "vintage", label: "Vintage", desc: "Warm grain overlay" },
  { id: "frame", label: "Frame", desc: "Subtle border frame" },
  { id: "stripe", label: "Stripe", desc: "Accent bar above title" },
];

const TYPOGRAPHY_OPTIONS = [
  { id: "sans", label: "Sans", preview: "Aa" },
  { id: "serif", label: "Serif", preview: "Aa" },
  { id: "modern", label: "Modern", preview: "Aa" },
  { id: "timeless", label: "Timeless", preview: "Aa" },
  { id: "bold", label: "Bold", preview: "Aa" },
  { id: "subtle", label: "Subtle", preview: "Aa" },
];

const COLOR_PALETTES = [
  { id: "light", label: "Light", color: "#ffffff" },
  { id: "gold", label: "Gold", color: "#fef3c7" },
  { id: "rose", label: "Rose", color: "#fff1f2" },
  { id: "terracotta", label: "Terracotta", color: "#ffedd5" },
  { id: "sand", label: "Sand", color: "#f5f5f4" },
  { id: "olive", label: "Olive", color: "#f7fee7" },
];

const TYPOGRAPHY_CLASSES = {
  sans: "font-sans",
  serif: "font-serif",
  modern: "font-sans tracking-tight",
  timeless: "font-serif italic",
  bold: "font-sans font-bold",
  subtle: "font-sans font-light tracking-wide",
};

export default function GalleryDesignPage() {
  const { gallery, setGallery, slug, isMountedRef } = useOutletContext();
  const toast = useToast();

  const saved = gallery?.design_settings || {};
  const [design, setDesign] = useState({
    layout: saved.layout || "center",
    typography: saved.typography || "serif",
    colorPalette: saved.colorPalette || "light",
    thumbSize: saved.thumbSize || "regular",
    gridSpacing: saved.gridSpacing ?? 16,
    gridStyle: saved.gridStyle || "vertical",
  });

  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("cover");

  const update = (key, value) => {
    const next = { ...design, [key]: value };
    setDesign(next);
    persistDesign(next);
  };

  const persistDesign = async (settings) => {
    if (saving) return;
    setSaving(true);
    try {
      const updated = await galleriesApi.updateGallery(slug, { design_settings: settings });
      if (isMountedRef?.current !== false) {
        setGallery((prev) => ({ ...prev, ...updated }));
        toast("Design settings saved", "success");
      }
    } catch {
      toast("Failed to save design settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const tabs = [
    { id: "cover", label: "Cover" },
    { id: "typography", label: "Typography" },
    { id: "color", label: "Color" },
    { id: "grid", label: "Grid" },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      {/* Controls panel */}
      <div className="lg:col-span-2 space-y-6">
        {/* Tab bar */}
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 px-4 py-2.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${
                activeTab === tab.id
                  ? "bg-white text-ink shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Cover Tab */}
        {activeTab === "cover" && (
          <div className="space-y-8">
            <Section title="Cover Layout">
              <div className="grid grid-cols-3 gap-3">
                {COVER_LAYOUTS.map((layout) => (
                  <button
                    key={layout.id}
                    onClick={() => update("layout", layout.id)}
                    className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-all cursor-pointer ${
                      design.layout === layout.id
                        ? "bg-teal-500/10 border-teal-500/30 text-teal-700"
                        : "bg-white border-slate-200 text-muted hover:border-slate-300 hover:text-ink"
                    }`}
                  >
                    <div className={`w-16 h-12 rounded-lg border ${
                      design.layout === layout.id ? "border-teal-400/40" : "border-slate-200"
                    } bg-slate-50 flex items-center justify-center`}>
                      <LayoutThumbnail type={layout.id} active={design.layout === layout.id} />
                    </div>
                    <span className="text-xs font-medium">{layout.label}</span>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Cover Photo">
              <p className="text-xs text-muted mb-3">
                Select a photo from your gallery to use as the cover hero image.
              </p>
              <div className="grid grid-cols-4 gap-2">
                {(gallery?.photos || []).slice(0, 8).map((photo) => (
                  <button
                    key={photo.id}
                    onClick={() => update("coverPhoto", photo.id)}
                    className={`aspect-square rounded-xl overflow-hidden border-2 transition-all cursor-pointer ${
                      design.coverPhoto === photo.id
                        ? "border-teal-500 ring-2 ring-teal-500/20"
                        : "border-transparent hover:border-slate-300"
                    }`}
                  >
                    <img
                      src={photo.thumbnail_url || photo.display_url}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
                {(!gallery?.photos || gallery.photos.length === 0) && (
                  <div className="col-span-4 py-8 text-center text-xs text-muted bg-slate-50 rounded-xl border border-dashed border-slate-200">
                    Upload photos first to select a cover image.
                  </div>
                )}
              </div>
            </Section>
          </div>
        )}

        {/* Typography Tab */}
        {activeTab === "typography" && (
          <div className="space-y-8">
            <Section title="Font Family">
              <div className="grid grid-cols-3 gap-3">
                {TYPOGRAPHY_OPTIONS.map((typo) => (
                  <button
                    key={typo.id}
                    onClick={() => update("typography", typo.id)}
                    className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-all cursor-pointer ${
                      design.typography === typo.id
                        ? "bg-teal-500/10 border-teal-500/30 text-teal-700"
                        : "bg-white border-slate-200 text-muted hover:border-slate-300 hover:text-ink"
                    }`}
                  >
                    <span className={`text-2xl ${TYPOGRAPHY_CLASSES[typo.id]}`}>{typo.preview}</span>
                    <span className="text-xs font-medium">{typo.label}</span>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Typography Preview">
              <div className="bg-slate-50 rounded-xl p-6 border border-slate-200">
                <h3 className={`text-2xl mb-2 ${TYPOGRAPHY_CLASSES[design.typography]} text-ink`}>
                  {gallery?.title || "Collection Title"}
                </h3>
                <div className="h-px w-8 bg-ink/15 mb-3" />
                <p className={`text-xs uppercase tracking-[0.2em] text-muted ${TYPOGRAPHY_CLASSES[design.typography]}`}>
                  {gallery?.event_date || "Event Date"}
                </p>
              </div>
            </Section>
          </div>
        )}

        {/* Color Tab */}
        {activeTab === "color" && (
          <div className="space-y-8">
            <Section title="Color Theme">
              <div className="grid grid-cols-3 gap-3">
                {COLOR_PALETTES.map((palette) => (
                  <button
                    key={palette.id}
                    onClick={() => update("colorPalette", palette.id)}
                    className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-all cursor-pointer ${
                      design.colorPalette === palette.id
                        ? "border-teal-500/40 ring-2 ring-teal-500/10"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div
                      className="w-12 h-12 rounded-xl border border-slate-200 shadow-inner"
                      style={{ backgroundColor: palette.color }}
                    />
                    <span className="text-xs font-medium text-muted">{palette.label}</span>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Color Preview">
              <div className="bg-slate-50 rounded-xl p-6 border border-slate-200">
                <ColorPreview palette={design.colorPalette} title={gallery?.title} />
              </div>
            </Section>
          </div>
        )}

        {/* Grid Tab */}
        {activeTab === "grid" && (
          <div className="space-y-8">
            <Section title="Grid Style">
              <div className="flex gap-3">
                {["vertical", "horizontal"].map((style) => (
                  <button
                    key={style}
                    onClick={() => update("gridStyle", style)}
                    className={`flex-1 px-4 py-3 rounded-xl text-xs font-medium capitalize border transition-all cursor-pointer ${
                      design.gridStyle === style
                        ? "bg-teal-500/10 border-teal-500/30 text-teal-700"
                        : "bg-white border-slate-200 text-muted hover:border-slate-300 hover:text-ink"
                    }`}
                  >
                    {style === "vertical" ? "Vertical Masonry" : "Horizontal Grid"}
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Thumbnail Size">
              <div className="flex gap-3">
                {["regular", "large"].map((size) => (
                  <button
                    key={size}
                    onClick={() => update("thumbSize", size)}
                    className={`flex-1 px-4 py-3 rounded-xl text-xs font-medium capitalize border transition-all cursor-pointer ${
                      design.thumbSize === size
                        ? "bg-teal-500/10 border-teal-500/30 text-teal-700"
                        : "bg-white border-slate-200 text-muted hover:border-slate-300 hover:text-ink"
                    }`}
                  >
                    {size === "regular" ? "Regular Thumbnails" : "Large Thumbnails"}
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Grid Spacing">
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="4"
                  max="32"
                  value={design.gridSpacing}
                  onChange={(e) => update("gridSpacing", Number(e.target.value))}
                  className="flex-1 h-1.5 bg-slate-200 rounded-full appearance-none cursor-pointer accent-teal-600"
                />
                <span className="text-xs text-muted font-mono w-12 text-right">{design.gridSpacing}px</span>
              </div>
            </Section>

            <Section title="Grid Preview">
              <div
                className={`grid gap-1 rounded-xl overflow-hidden ${
                  design.gridStyle === "vertical" ? "grid-cols-4" : "grid-cols-3"
                }`}
                style={{ gap: `${Math.max(2, design.gridSpacing / 4)}px` }}
              >
                {Array.from({ length: design.gridStyle === "vertical" ? 8 : 6 }).map((_, i) => (
                  <div
                    key={i}
                    className={`bg-slate-200 rounded-lg ${
                      design.thumbSize === "large" ? "aspect-square" : design.gridStyle === "vertical" ? "aspect-[3/4]" : "aspect-[4/3]"
                    }`}
                  />
                ))}
              </div>
            </Section>
          </div>
        )}
      </div>

      {/* Live preview */}
      <div className="space-y-4">
        <div className="sticky top-24">
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Live Preview</h3>
          <CoverPreview settings={design} gallery={gallery} />
          <p className="text-[10px] text-muted mt-2 text-center">This is how clients will see your gallery cover</p>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-ink/80 mb-3">{title}</h3>
      {children}
    </div>
  );
}

function LayoutThumbnail({ type, active }) {
  const color = active ? "bg-teal-400" : "bg-slate-300";
  return (
    <div className="w-full h-full flex items-center justify-center">
      {type === "center" && <div className={`w-6 h-1 rounded ${color}`} />}
      {type === "left" && <div className={`w-4 h-1 rounded ${color} ml-1`} />}
      {type === "novel" && (
        <div className="w-6 h-4 border border-current rounded-sm relative" style={{ color: active ? "#14b8a6" : "#94a3b8" }}>
          <div className="absolute top-0.5 left-0.5 w-1.5 h-1 border-t border-l border-current" />
        </div>
      )}
      {type === "vintage" && <div className={`w-6 h-4 rounded ${color} opacity-60`} />}
      {type === "frame" && <div className="w-6 h-4 border-2 border-current rounded-sm" style={{ color: active ? "#14b8a6" : "#94a3b8" }} />}
      {type === "stripe" && <div className={`w-1 h-4 rounded-full ${color}`} />}
    </div>
  );
}

function ColorPreview({ palette, title }) {
  const themes = {
    light: { bg: "bg-white", text: "text-ink" },
    gold: { bg: "bg-amber-50", text: "text-amber-900" },
    rose: { bg: "bg-rose-50", text: "text-rose-900" },
    terracotta: { bg: "bg-orange-50", text: "text-orange-900" },
    sand: { bg: "bg-stone-100", text: "text-stone-900" },
    olive: { bg: "bg-lime-50", text: "text-lime-900" },
  };
  const theme = themes[palette] || themes.light;
  return (
    <div className={`${theme.bg} rounded-xl p-6 text-center`}>
      <h4 className={`text-lg font-serif ${theme.text}`}>{title || "Collection Title"}</h4>
      <div className="h-px w-6 bg-current/15 mx-auto my-2" />
      <p className="text-[10px] uppercase tracking-[0.2em] text-muted">Preview</p>
    </div>
  );
}
