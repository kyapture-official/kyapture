import { Link } from "react-router-dom";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, ChevronDown } from "lucide-react";

const navLinks = [
  {
    label: "Products",
    children: [
      { label: "Client Gallery", href: "#gallery" },
      { label: "Portfolio Website", href: "#features" },
      { label: "Studio Manager", href: "#features" },
      { label: "Store", href: "#features" },
      { label: "AI Culling", href: "#features" },
    ],
  },
  { label: "Pricing", href: "#stats" },
  { label: "Resources", href: "#testimonials" },
  { label: "Enterprise", href: "#cta" },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "border-b border-white/5 bg-[#0A0E1A]/80 backdrop-blur-md shadow-lg shadow-black/20"
          : "bg-transparent"
      }`}
    >
      <nav className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <a href="#" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-teal-500 flex items-center justify-center">
              <span className="text-[#0A0E1A] font-bold text-sm">K</span>
            </div>
            <span className="text-xl font-bold tracking-tight text-white">
              Kyapture
            </span>
          </a>

          <div className="hidden lg:flex items-center gap-1">
            {navLinks.map((link) => (
              <div
                key={link.label}
                className="relative"
                onMouseEnter={() =>
                  link.children && setActiveDropdown(link.label)
                }
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <a
                  href={link.href || "#"}
                  className="flex items-center gap-1 rounded-lg px-4 py-2 text-sm font-medium text-slate-400 transition-colors hover:text-white hover:bg-white/5"
                >
                  {link.label}
                  {link.children && (
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${
                        activeDropdown === link.label ? "rotate-180" : ""
                      }`}
                    />
                  )}
                </a>

                <AnimatePresence>
                  {link.children && activeDropdown === link.label && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 8 }}
                      transition={{ duration: 0.2 }}
                      className="absolute top-full left-0 mt-1 w-56 rounded-xl border border-slate-700/50 bg-slate-900/90 p-2 shadow-xl backdrop-blur-xl"
                    >
                      {link.children.map((child) => (
                        <a
                          key={child.label}
                          href={child.href}
                          className="block rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
                        >
                          {child.label}
                        </a>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>

          <div className="hidden lg:flex items-center gap-3">
            <Link
              to="/login"
              className="rounded-lg px-4 py-2 text-sm font-medium text-slate-400 transition-colors hover:text-white"
            >
              Log In
            </Link>
            <Link
              to="/register"
              className="rounded-full bg-teal-500 px-5 py-2.5 text-sm font-semibold text-[#0A0E1A] shadow-[0_0_20px_rgba(13,148,136,0.3)] transition-all hover:bg-teal-400 hover:shadow-[0_0_30px_rgba(13,148,136,0.4)]"
            >
              Get Started
            </Link>
          </div>

          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="lg:hidden rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white"
          >
            {mobileOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="lg:hidden border-t border-white/5 bg-[#0A0E1A]/95 backdrop-blur-md"
          >
            <div className="space-y-1 px-6 py-4">
              {navLinks.map((link) => (
                <div key={link.label}>
                  <a
                    href={link.href || "#"}
                    className="block rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-white"
                    onClick={() => setMobileOpen(false)}
                  >
                    {link.label}
                  </a>
                  {link.children?.map((child) => (
                    <a
                      key={child.label}
                      href={child.href}
                      className="block rounded-lg pl-6 pr-3 py-2 text-sm text-slate-500 hover:bg-white/5 hover:text-slate-300"
                      onClick={() => setMobileOpen(false)}
                    >
                      {child.label}
                    </a>
                  ))}
                </div>
              ))}
              <div className="pt-4 border-t border-white/5 space-y-2">
                <Link
                  to="/login"
                  className="block text-center rounded-lg px-4 py-2.5 text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-white"
                  onClick={() => setMobileOpen(false)}
                >
                  Log In
                </Link>
                <Link
                  to="/register"
                  className="block text-center rounded-full bg-teal-500 px-5 py-2.5 text-sm font-semibold text-[#0A0E1A]"
                  onClick={() => setMobileOpen(false)}
                >
                  Get Started
                </Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
