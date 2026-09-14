import { useEffect, useRef, useState } from 'react';
import {
  motion,
  useMotionValue,
  useSpring,
  useTransform,
  type MotionValue,
} from 'framer-motion';
import { ArrowRight, Camera, CheckCircle2, Lock } from 'lucide-react';

const stagger = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12,
    },
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] as const },
  },
};

type GridImage = {
  src: string;
  label: string;
  exif: string;
  colors: string[];
};

const gridImages: GridImage[] = [
  {
    src: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=500&h=600&fit=crop',
    label: 'Wedding',
    exif: '50mm  f/1.8  1/200s',
    colors: ['bg-amber-700', 'bg-stone-800', 'bg-orange-200', 'bg-teal-900'],
  },
  {
    src: 'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=500&h=600&fit=crop',
    label: 'Portrait',
    exif: '85mm  f/2.0  1/320s',
    colors: ['bg-stone-700', 'bg-amber-600', 'bg-orange-900', 'bg-neutral-500'],
  },
  {
    src: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=500&h=600&fit=crop',
    label: 'Landscape',
    exif: '24mm  f/8.0  1/125s',
    colors: ['bg-cyan-900', 'bg-slate-800', 'bg-blue-800', 'bg-emerald-700'],
  },
  {
    src: 'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=500&h=600&fit=crop',
    label: 'Adventure',
    exif: '35mm  f/4.0  1/500s',
    colors: ['bg-orange-500', 'bg-amber-800', 'bg-yellow-900', 'bg-stone-700'],
  },
  {
    src: 'https://images.unsplash.com/photo-1515934751635-c81c6bc9a2d8?w=500&h=600&fit=crop',
    label: 'Editorial',
    exif: '105mm  f/2.8  1/250s',
    colors: ['bg-rose-900', 'bg-stone-900', 'bg-pink-700', 'bg-neutral-800'],
  },
  {
    src: 'https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=500&h=600&fit=crop',
    label: 'Commercial',
    exif: '70mm  f/5.6  1/160s',
    colors: ['bg-teal-800', 'bg-cyan-700', 'bg-slate-700', 'bg-emerald-900'],
  },
];

const CornerBracket = ({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) => {
  const map: Record<typeof position, string> = {
    tl: 'top-3 left-3 border-t-2 border-l-2',
    tr: 'top-3 right-3 border-t-2 border-r-2',
    bl: 'bottom-3 left-3 border-b-2 border-l-2',
    br: 'bottom-3 right-3 border-b-2 border-r-2',
  };
  return (
    <div className={`absolute h-5 w-5 ${map[position]} border-slate-500/50`} />
  );
};

export default function Hero() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [isCoarse, setIsCoarse] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(hover: none), (pointer: coarse)');
    const handle = () => setIsCoarse(mql.matches || window.innerWidth < 1024);
    handle();
    mql.addEventListener?.('change', handle);
    window.addEventListener('resize', handle);
    return () => {
      mql.removeEventListener?.('change', handle);
      window.removeEventListener('resize', handle);
    };
  }, []);

  const mouseX: MotionValue<number> = useMotionValue(0);
  const mouseY: MotionValue<number> = useMotionValue(0);

  const springX = useSpring(mouseX, { stiffness: 350, damping: 30, mass: 0.4 });
  const springY = useSpring(mouseY, { stiffness: 350, damping: 30, mass: 0.4 });

  const rotateY = useTransform(springX, [-1, 1], isCoarse ? [0, 0] : [-7, 7]);
  const rotateX = useTransform(springY, [-1, 1], isCoarse ? [0, 0] : [5, -5]);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isCoarse || !stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const y = ((e.clientY - rect.top) / rect.height) * 2 - 1;
    mouseX.set(x);
    mouseY.set(y);
  };

  const handleMouseLeave = () => {
    mouseX.set(0);
    mouseY.set(0);
  };

  return (
    <section className="relative min-h-screen overflow-hidden bg-[#0A0E1A] pt-24 pb-20 lg:pt-32 lg:pb-28">
      {/* ─── Ambient Background ─── */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        {/* Teal orb */}
        <motion.div
          aria-hidden
          animate={{ scale: [1, 1.2, 1], x: [0, 30, 0], y: [0, -20, 0] }}
          transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -left-32 -top-32 h-[500px] w-[500px] rounded-full bg-[#14b8a6] opacity-30 blur-[120px]"
        />
        {/* Emerald orb */}
        <motion.div
          aria-hidden
          animate={{ scale: [1, 1.15, 1], x: [0, -25, 0], y: [0, 25, 0] }}
          transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
          className="absolute -right-20 top-1/4 h-[450px] w-[450px] rounded-full bg-[#10b981] opacity-30 blur-[120px]"
        />
        {/* Indigo orb */}
        <motion.div
          aria-hidden
          animate={{ scale: [1, 1.18, 1], x: [0, 20, 0], y: [0, -15, 0] }}
          transition={{ duration: 16, repeat: Infinity, ease: 'easeInOut', delay: 4 }}
          className="absolute -bottom-20 left-1/3 h-[400px] w-[400px] rounded-full bg-[#6366f1] opacity-30 blur-[120px]"
        />
        {/* Grid overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293715_1px,transparent_1px),linear-gradient(to_bottom,#1f293715_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      </div>

      <div className="relative z-10 mx-auto max-w-7xl px-6 lg:px-8">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* ─── Left Column ─── */}
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="max-w-xl"
          >
            <motion.div
              variants={fadeUp}
              className="mb-8 inline-flex items-center gap-2 rounded-full border border-teal-500/30 bg-teal-950/40 px-4 py-1.5 text-sm backdrop-blur-md"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-teal-400" />
              </span>
              <span className="text-xs font-semibold uppercase tracking-widest text-teal-400">
                Trusted by 50,000+ Photographers
              </span>
            </motion.div>

            <motion.h1
              variants={fadeUp}
              className="text-5xl font-extrabold leading-[1.05] tracking-tight text-white md:text-6xl"
            >
              <span className="block text-white">Designed for Photographers.</span>
              <span className="mt-2 block bg-gradient-to-r from-teal-400 via-emerald-400 to-cyan-300 bg-clip-text text-transparent">
                Built to Elevate Your Craft.
              </span>
            </motion.h1>

            <motion.p
              variants={fadeUp}
              className="mt-6 text-lg leading-relaxed text-slate-400"
            >
              From proofing and client galleries to asset delivery, studio management,
              and AI-powered culling — Kyapture is the end-to-end platform that
              handles your entire photography workflow.
            </motion.p>

            <motion.div
              variants={fadeUp}
              className="mt-8 flex flex-wrap items-center gap-4"
            >
              <motion.a
                href="#"
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.98 }}
                className="group inline-flex items-center gap-2 rounded-full bg-teal-500 px-7 py-3.5 text-sm font-semibold text-slate-950 shadow-[0_0_25px_rgba(13,148,136,0.4)] transition-colors duration-300 hover:bg-teal-400 hover:shadow-[0_0_35px_rgba(13,148,136,0.6)]"
              >
                Get Started Free
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
              </motion.a>
              <a
                href="#features"
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-300 transition-colors duration-200 hover:text-white"
              >
                See how it works
                <ArrowRight className="h-3.5 w-3.5" />
              </a>
            </motion.div>

            <motion.div
              variants={fadeUp}
              className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500"
            >
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-teal-500/60" />
                No credit card required
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-teal-500/60" />
                14-day free trial
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-teal-500/60" />
                Cancel anytime
              </span>
            </motion.div>
          </motion.div>

          {/* ─── Right Column — 3D Parallax Camera HUD ─── */}
          <div
            ref={stageRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={{ perspective: 1200 }}
            className="relative hidden h-[560px] w-full lg:block"
          >
            <motion.div
              style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }}
              className="relative h-full w-full"
            >
              {/* Floating pill · top-left (behind) — Wedding collection */}
              <motion.div
                style={{ translateZ: -40 }}
                initial={{ opacity: 0, x: -20, y: -10 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                transition={{ duration: 0.7, delay: 1.0, ease: [0.16, 1, 0.3, 1] }}
                className="absolute -left-2 top-10 z-0"
              >
                <motion.div
                  animate={{ y: [0, -10, 0] }}
                  transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
                  className="flex items-center gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4 shadow-2xl backdrop-blur-xl"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/15">
                    <Camera className="h-5 w-5 text-emerald-400" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">Wedding</p>
                    <p className="text-xs text-slate-400">248 photos</p>
                  </div>
                </motion.div>
              </motion.div>

              {/* Floating pill · top-right (behind) */}
              <motion.div
                style={{ translateZ: -20 }}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.7, delay: 1.2, ease: [0.16, 1, 0.3, 1] }}
                className="absolute -right-2 top-2 z-0"
              >
                <motion.div
                  animate={{ y: [0, -8, 0] }}
                  transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut', delay: 1.5 }}
                  className="flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3.5 py-1.5 shadow-[0_0_20px_rgba(16,185,129,0.25)] backdrop-blur-xl"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                    Live session
                  </span>
                </motion.div>
              </motion.div>

              {/* Floating pill · bottom-right (overlapping main window) */}
              <motion.div
                style={{ translateZ: 30 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 1.4, ease: [0.16, 1, 0.3, 1] }}
                className="absolute -bottom-2 -right-2 z-30"
              >
                <motion.div
                  animate={{ y: [0, -12, 0] }}
                  transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut', delay: 0.5 }}
                  className="flex items-center gap-2.5 rounded-2xl border border-amber-400/30 bg-slate-900/80 px-4 py-2.5 shadow-2xl backdrop-blur-xl"
                >
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/20">
                    <Lock className="h-3.5 w-3.5 text-amber-400" />
                  </span>
                  <div>
                    <p className="text-xs font-semibold text-white">
                      Gallery unlocked
                    </p>
                    <p className="text-[10px] font-medium text-slate-400">
                      Miller Wedding · 248 photos
                    </p>
                  </div>
                </motion.div>
              </motion.div>

              {/* Main Gallery Window with Shutter-Open Entrance */}
              <motion.div
                style={{ translateZ: 60 }}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{
                  duration: 0.9,
                  delay: 0.4,
                  type: 'spring',
                  stiffness: 140,
                  damping: 16,
                  mass: 0.9,
                }}
                className="absolute left-6 right-6 top-20 z-10"
              >
                <div className="relative overflow-hidden rounded-2xl border border-slate-700/50 bg-slate-900/60 p-2 shadow-2xl backdrop-blur-2xl">
                  {/* Camera HUD overlays */}
                  <CornerBracket position="tl" />
                  <CornerBracket position="tr" />
                  <CornerBracket position="bl" />
                  <CornerBracket position="br" />

                  {/* Pulsing REC indicator */}
                  <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2">
                    <div className="flex items-center gap-1.5 rounded-full border border-red-500/30 bg-black/40 px-2.5 py-1 backdrop-blur-md">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
                      </span>
                      <span className="font-mono text-[10px] font-bold tracking-widest text-red-400">
                        REC
                      </span>
                    </div>
                  </div>

                  {/* Live exposure values */}
                  <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
                    <div className="rounded-md border border-slate-700/60 bg-black/50 px-3 py-1 font-mono text-[10px] tracking-wider text-slate-300 backdrop-blur-md">
                      1/800s • f/1.4 • ISO 100
                    </div>
                  </div>

                  {/* Mac-style window controls (top-left) */}
                  <div className="absolute left-4 top-3 z-20 flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
                  </div>

                  <div className="rounded-xl bg-slate-950/40 p-4 pt-10">
                    <div className="grid grid-cols-3 gap-3">
                      {gridImages.map((img, i) => (
                        <motion.div
                          key={img.label}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{
                            duration: 0.5,
                            delay: 0.9 + i * 0.07,
                            ease: [0.16, 1, 0.3, 1],
                          }}
                          className="group relative aspect-[4/5] cursor-pointer overflow-hidden rounded-xl border border-slate-800/60"
                        >
                          <img
                            src={img.src}
                            alt={img.label}
                            className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
                            loading="lazy"
                          />

                          {/* Bottom gradient overlay */}
                          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

                          {/* Top-right tag */}
                          <div className="absolute right-2 top-2 rounded-md bg-black/50 px-1.5 py-0.5 font-mono text-[9px] text-white/80 opacity-0 backdrop-blur-sm transition-opacity duration-300 group-hover:opacity-100">
                            RAW
                          </div>

                          {/* Label + EXIF */}
                          <div className="absolute inset-x-0 bottom-0 translate-y-2 px-3 pb-2.5 opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
                            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-white">
                              {img.label}
                            </p>
                            <p className="font-mono text-[9px] text-teal-300">
                              {img.exif}
                            </p>
                            {/* Color Extractor Palette */}
                            <div className="mt-2 flex gap-1.5">
                              {img.colors.map((c, idx) => (
                                <motion.span
                                  key={idx}
                                  initial={{ opacity: 0, scale: 0.6 }}
                                  whileInView={{ opacity: 1, scale: 1 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  className={`h-3.5 w-3.5 rounded-full ${c} ring-1 ring-white/20 shadow-sm`}
                                />
                              ))}
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}