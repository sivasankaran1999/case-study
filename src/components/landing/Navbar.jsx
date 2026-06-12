import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Logo from "../Logo";

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 border-b bg-white transition-shadow duration-300 ${
        scrolled ? "border-ps-border shadow-card" : "border-ps-border/60"
      }`}
    >
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-20 items-center justify-between">
          <Link to="/" className="flex items-center">
            <Logo size="lg" showAI={false} />
          </Link>

          <Link
            to="/chat"
            className="group inline-flex items-center gap-1.5 rounded-lg bg-ps-teal px-4 py-2 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-ps-tealDark"
          >
            Try the AI Assistant
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </nav>
    </header>
  );
};

export default Navbar;
