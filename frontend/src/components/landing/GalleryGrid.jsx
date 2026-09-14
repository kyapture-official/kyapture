import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Camera, Aperture, Clock, Gauge, Focus } from 'lucide-react';

type Category = 'All' | 'Wedding' | 'Portrait' | 'Editorial' | 'Commercial';

interface GalleryImage {
  id: number;
  src: string;
  category: Category;
  exif: {
    aperture: string;
    shutter: string;
    iso: string;
    focal: string;
  };
  span: string;
}

const categories: Category[] = ['All', 'Wedding', 'Portrait', 'Editorial', 'Commercial'];

const galleryImages: GalleryImage[] = [
  {
    id: 1,
    src: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=600&h=800&fit=crop',
    category: 'Wedding',
    exif: { aperture: 'f/2.8', shutter: '1/250s', iso: '200', focal: '85mm' },
    span: 'row-span-2',
  },
  {
    id: 2,
    src: 'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=600&h=400&fit=crop',
    category: 'Portrait',
    exif: { aperture: 'f/1.4', shutter: '1/500s', iso: '100', focal: '50mm' },
    span: '',
  },
  {
    id: 3,
    src: 'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=600&h=400&fit=crop',
    category: 'Commercial',
    exif: { aperture: 'f/5.6', shutter: '1/125s', iso: '400', focal: '35mm' },
    span: '',
  },
  {
    id: 4,
    src: 'https://images.unsplash.com/photo-1515934751635-c81c6bc9a2d8?w=600&h=800&fit=crop',
    category: 'Portrait',
    exif: { aperture: 'f/2.0', shutter: '1/320s', iso: '160', focal: '105mm' },
    span: 'row-span-2',
  },
  {
    id: 5,
    src: 'https://images.unsplash.com/photo-1606216794074-735e91aa2c92?w=600&h=400&fit=crop',
    category: 'Wedding',
    exif: { aperture: 'f/1.8', shutter: '1/640s', iso: '100', focal: '70mm' },
    span: '',
  },
  {
    id: 6,
    src: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600&h=900&fit=crop',
    category: 'Editorial',
    exif: { aperture: 'f/4.0', shutter: '1/200s', iso: '320', focal: '24mm' },
    span: 'row-span-2',
  },
  {
    id: 7,
    src: 'https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=600&h=400&fit=crop',
    category: 'Commercial',
    exif: { aperture: 'f/8.0', shutter: '1/60s', iso: '200', focal: '50mm' },
    span: '',
  },
  {
    id: 8,
    src: 'https://images.unsplash.com/photo-1465495976277-4387d4b0b4c6?w=600&h=400&fit=crop',
    category: 'Wedding',
    exif: { aperture: 'f/2.8', shutter: '1/200s', iso: '250', focal: '135mm' },
    span: '',
  },
  {
    id: 9,
    src: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&h=800&fit=crop',
    category: 'Editorial',
    exif: { aperture: 'f/2.0', shutter: '1/400s', iso: '100', focal: '85mm' },
    span: 'row-span-2',
  },
  {
    id: 10,
    src: 'https://images.unsplash.com/photo-1504703395950-b89145a5425b?w=600&h=400&fit=crop',
    category: 'Portrait',
    exif: { aperture: 'f/1.8', shutter: '1/320s', iso: '125', focal: '60mm' },
    span: '',
  },
  {
    id: 11,
    src: 'https://images.unsplash.com/photo-1471341971476-ae15ff5dd4ea?w=600&h=400&fit=crop',
    category: 'Commercial',
    exif: { aperture: 'f/5.6', shutter: '1/160s', iso: '320', focal: '28mm' },
    span: '',
  },
  {
    id: 12,
    src: 'https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=600&h=800&fit=crop',
    category: 'Editorial',
    exif: { aperture: 'f/2.8', shutter: '1/250s', iso: '200', focal: '70mm' },
    span: 'row-span-2',
  },
];

export default function GalleryGrid() {
  const [activeCategory, setActiveCategory] = useState<Category>('All');
  const [hoveredImage, setHoveredImage] = useState<number | null>(null);

  const filtered =
    activeCategory === 'All'
      ? galleryImages
      : galleryImages.filter((img) => img.category === activeCategory);

  return (
    <section id="gallery" className="py-24 bg-white">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Your Work, Beautifully Showcased
          </h2>
          <p className="mt-4 text-lg text-slate-500 max-w-2xl mx-auto">
            Create stunning client galleries with EXIF data overlays and category filtering that
            wows your clients every time.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="flex flex-wrap justify-center gap-2 mb-10"
        >
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`relative rounded-full px-5 py-2 text-sm font-medium transition-colors ${
                activeCategory === cat
                  ? 'text-white'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
              }`}
            >
              {activeCategory === cat && (
                <motion.div
                  layoutId="galleryTab"
                  className="absolute inset-0 rounded-full bg-primary"
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                />
              )}
              <span className="relative z-10">{cat}</span>
            </button>
          ))}
        </motion.div>

        <motion.div layout className="columns-2 md:columns-3 lg:columns-4 gap-4 space-y-4">
          <AnimatePresence mode="popLayout">
            {filtered.map((img) => (
              <motion.div
                key={img.id}
                layout
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="relative break-inside-avoid group cursor-pointer"
                onMouseEnter={() => setHoveredImage(img.id)}
                onMouseLeave={() => setHoveredImage(null)}
              >
                <div className="relative overflow-hidden rounded-2xl">
                  <img
                    src={img.src}
                    alt={`${img.category} photography`}
                    className="w-full object-cover transition-transform duration-500 group-hover:scale-105"
                    loading="lazy"
                  />
                  <div
                    className={`absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent transition-opacity duration-300 ${
                      hoveredImage === img.id ? 'opacity-100' : 'opacity-0'
                    }`}
                  >
                    <div className="absolute bottom-0 left-0 right-0 p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <Camera className="h-3.5 w-3.5 text-white/70" />
                        <span className="text-xs font-medium text-white/90 uppercase tracking-wider">
                          {img.category}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                        <div className="flex items-center gap-1.5">
                          <Aperture className="h-3 w-3 text-teal-300" />
                          <span className="text-[11px] text-white/80">{img.exif.aperture}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Clock className="h-3 w-3 text-teal-300" />
                          <span className="text-[11px] text-white/80">{img.exif.shutter}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Gauge className="h-3 w-3 text-teal-300" />
                          <span className="text-[11px] text-white/80">ISO {img.exif.iso}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Focus className="h-3 w-3 text-teal-300" />
                          <span className="text-[11px] text-white/80">{img.exif.focal}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      </div>
    </section>
  );
}
