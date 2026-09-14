// frontend/src/pages/LandingPage.jsx
import Navbar from '../components/landing/Navbar';
import Hero from '../components/landing/Hero';
import GalleryGrid from '../components/landing/GalleryGrid';
import Features from '../components/landing/Features';
import StatsTestimonials from '../components/landing/StatsTestimonials';
import Footer from '../components/landing/Footer';

export default function LandingPage() {
  return (
    <div className="font-landing min-h-screen bg-offwhite text-slate-900 antialiased">
      <Navbar />
      <Hero />
      <GalleryGrid />
      <Features />
      <StatsTestimonials />
      <Footer />
    </div>
  );
}