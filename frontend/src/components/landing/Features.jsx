import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Images,
  Globe,
  LayoutDashboard,
  Sparkles,
  ShieldCheck,
  MousePointerClick,
  CreditCard,
  Wand2,
} from 'lucide-react';

const features = [
  {
    id: 'gallery',
    icon: Images,
    title: 'Client Gallery',
    description:
      'High-resolution proofing, digital downloads, and pin-protected client access. Deliver collections that dazzle.',
    color: 'from-teal-500 to-emerald-500',
    preview: {
      title: 'Wedding Collection — Sarah & James',
      items: ['248 Curated Photos', 'Online Proofing Active', 'Download Link: 3 days left', 'Client Pin: ••••7291'],
      gradient: 'from-teal-500/20 to-emerald-500/20',
    },
    capabilities: [ShieldCheck, MousePointerClick],
  },
  {
    id: 'portfolio',
    icon: Globe,
    title: 'Portfolio Website',
    description:
      'Drag-and-drop customization with zero code. Build a stunning portfolio site that reflects your brand.',
    color: 'from-violet-500 to-purple-500',
    preview: {
      title: 'studio.luminaweddings.com',
      items: ['Custom Domain Connected', '8 Pages Published', 'SEO Score: 98/100', 'SSL Certificate Active'],
      gradient: 'from-violet-500/20 to-purple-500/20',
    },
    capabilities: [Globe, MousePointerClick],
  },
  {
    id: 'studio',
    icon: LayoutDashboard,
    title: 'Studio Manager',
    description:
      'Automated booking calendars, contracts, and digital invoice payment tracking — all in one place.',
    color: 'from-amber-500 to-orange-500',
    preview: {
      title: 'Upcoming Bookings',
      items: ['Dec 15 — Johnson Wedding ($3,200)', 'Dec 22 — Smith Family ($850)', 'Jan 3 — Corp Headshots ($1,500)', 'Invoices: 2 Pending'],
      gradient: 'from-amber-500/20 to-orange-500/20',
    },
    capabilities: [CreditCard, LayoutDashboard],
  },
  {
    id: 'ai',
    icon: Sparkles,
    title: 'AI Photo Editor & Culler',
    description:
      'Intelligent AI-driven sorting, tag selection, and color matching. Spend less time editing, more shooting.',
    color: 'from-rose-500 to-pink-500',
    preview: {
      title: 'AI Culling — 2,481 Raw Photos',
      items: ['Keepers Identified: 312', 'Duplicates Removed: 187', 'Focus Issues Flagged: 44', 'Time Saved: ~4.5 hrs'],
      gradient: 'from-rose-500/20 to-pink-500/20',
    },
    capabilities: [Wand2, Sparkles],
  },
];

export default function Features() {
  const [activeFeature, setActiveFeature] = useState(features[0].id);

  const current = features.find((f) => f.id === activeFeature);

  return (
    <section id="features" className="py-24 bg-offwhite">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Everything You Need to Run Your Studio
          </h2>
          <p className="mt-4 text-lg text-slate-500 max-w-2xl mx-auto">
            From first client inquiry to final gallery delivery, Kyapture handles your entire
            photography business workflow.
          </p>
        </motion.div>

        <div className="grid lg:grid-cols-5 gap-8 items-start">
          <div className="lg:col-span-2 space-y-3">
            {features.map((feat, i) => (
              <motion.button
                key={feat.id}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                onClick={() => setActiveFeature(feat.id)}
                className={`w-full text-left rounded-2xl p-5 transition-all duration-300 ${
                  activeFeature === feat.id
                    ? 'bg-white shadow-lg shadow-slate-200/60 border border-slate-100'
                    : 'hover:bg-white/60 border border-transparent'
                }`}
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${feat.color} shadow-sm`}
                  >
                    <feat.icon className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3
                      className={`text-base font-semibold transition-colors ${
                        activeFeature === feat.id ? 'text-slate-900' : 'text-slate-600'
                      }`}
                    >
                      {feat.title}
                    </h3>
                    <p className="mt-1 text-sm text-slate-500 leading-relaxed">
                      {feat.description}
                    </p>
                    <div className="mt-3 flex items-center gap-2">
                      {feat.capabilities.map((Cap, j) => (
                        <div
                          key={j}
                          className="flex items-center gap-1 rounded-full bg-slate-50 px-2.5 py-1"
                        >
                          <Cap className="h-3 w-3 text-slate-400" />
                          <span className="text-[11px] text-slate-500 font-medium">
                            {j === 0 ? 'Secure' : 'Easy'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.button>
            ))}
          </div>

          <div className="lg:col-span-3 hidden lg:block sticky top-24">
            <div className="relative rounded-3xl bg-charcoal p-6 shadow-2xl shadow-charcoal/20 min-h-[420px]">
              <div className="flex items-center gap-2 mb-5">
                <div className="h-3 w-3 rounded-full bg-red-400" />
                <div className="h-3 w-3 rounded-full bg-amber-400" />
                <div className="h-3 w-3 rounded-full bg-emerald-400" />
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={current.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className={`rounded-2xl bg-gradient-to-br ${current.preview.gradient} p-6 border border-white/10`}
                >
                  <div className="flex items-center gap-3 mb-5">
                    <current.icon className="h-5 w-5 text-white/80" />
                    <h4 className="text-sm font-semibold text-white">{current.preview.title}</h4>
                  </div>

                  <div className="space-y-3">
                    {current.preview.items.map((item, j) => (
                      <motion.div
                        key={j}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.1 + j * 0.08 }}
                        className="flex items-center gap-3 rounded-xl bg-white/5 px-4 py-3 backdrop-blur-sm border border-white/5"
                      >
                        <div className="h-2 w-2 rounded-full bg-primary" />
                        <span className="text-sm text-white/80">{item}</span>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
