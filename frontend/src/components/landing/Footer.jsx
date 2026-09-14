import { motion } from 'framer-motion';
import { ArrowRight, Globe, Mail, MessageCircle, Send } from 'lucide-react';

const footerLinks = {
  Products: [
    { label: 'Client Gallery', href: '#' },
    { label: 'Portfolio Website', href: '#' },
    { label: 'Studio Manager', href: '#' },
    { label: 'Digital Store', href: '#' },
    { label: 'AI Photo Editor', href: '#' },
  ],
  Resources: [
    { label: 'Blog', href: '#' },
    { label: 'Help Center', href: '#' },
    { label: 'Tutorials', href: '#' },
    { label: 'API Docs', href: '#' },
    { label: 'Community', href: '#' },
  ],
  Company: [
    { label: 'About Us', href: '#' },
    { label: 'Careers', href: '#' },
    { label: 'Press Kit', href: '#' },
    { label: 'Partners', href: '#' },
    { label: 'Contact', href: '#' },
  ],
  Legal: [
    { label: 'Privacy Policy', href: '#' },
    { label: 'Terms of Service', href: '#' },
    { label: 'Cookie Policy', href: '#' },
    { label: 'GDPR', href: '#' },
    { label: 'DPA', href: '#' },
  ],
};

const socials = [
  { icon: Globe, href: '#', label: 'Website' },
  { icon: MessageCircle, href: '#', label: 'Community' },
  { icon: Send, href: '#', label: 'Newsletter' },
  { icon: Mail, href: '#', label: 'Email' },
];

export default function Footer() {
  return (
    <>
      <section id="cta" className="py-24 bg-offwhite">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }}
            transition={{ duration: 0.5 }}
            className="relative rounded-3xl bg-charcoal p-12 sm:p-16 text-center overflow-hidden"
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_60%_at_50%_30%,rgba(13,148,136,0.15),transparent)]" />
            <div className="relative">
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white leading-tight">
                Start Your 14-Day Free Trial.
                <br />
                <span className="text-primary-light">No Credit Card Required.</span>
              </h2>
              <p className="mt-6 text-lg text-slate-400 max-w-xl mx-auto">
                Join 50,000+ photographers who trust Kyapture to manage their studio, deliver galleries,
                and grow their business.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-4">
                <a
                  href="#"
                  className="group inline-flex items-center gap-2 rounded-full bg-primary px-8 py-4 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:bg-primary-light hover:shadow-xl hover:shadow-primary/30"
                >
                  Get Started Free
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </a>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <footer className="bg-charcoal border-t border-white/5">
        <div className="mx-auto max-w-7xl px-6 lg:px-8 pt-16 pb-8">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-12">
            <div className="col-span-2 md:col-span-1">
              <a href="#" className="flex items-center gap-2 mb-4">
                <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                  <span className="text-white font-bold text-sm">K</span>
                </div>
                <span className="text-lg font-bold tracking-tight text-white">Kyapture</span>
              </a>
              <p className="text-sm text-slate-500 leading-relaxed max-w-xs">
                The all-in-one platform built for professional photographers who want to focus on their craft.
              </p>
              <div className="flex items-center gap-3 mt-5">
                {socials.map((social) => (
                  <a
                    key={social.label}
                    href={social.href}
                    aria-label={social.label}
                    className="h-9 w-9 rounded-lg bg-white/5 flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  >
                    <social.icon className="h-4 w-4" />
                  </a>
                ))}
              </div>
            </div>

            {Object.entries(footerLinks).map(([category, links]) => (
              <div key={category}>
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                  {category}
                </h4>
                <ul className="space-y-2.5">
                  {links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-slate-500 hover:text-white transition-colors"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="border-t border-white/5 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-xs text-slate-600">
              &copy; {new Date().getFullYear()} Kyapture. All rights reserved.
            </p>
            <p className="text-xs text-slate-600">
              Built with care for photographers everywhere.
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}
