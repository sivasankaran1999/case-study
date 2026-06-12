import React from "react";
import { Link } from "react-router-dom";
import { PARTSELECT_URL } from "../../styles/theme";
import Logo from "../Logo";

const Footer = () => {
  return (
    <footer className="bg-ps-tealDeep text-white">
      <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-3">
          {/* Brand */}
          <div>
            <Logo size="md" onDark />
            <p className="mt-3 text-sm text-white/70">
              AI-powered parts assistance
            </p>
          </div>

          {/* Quick links */}
          <div className="md:text-center">
            <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ps-gold">
              Quick Links
            </h4>
            <ul className="mt-4 space-y-2 text-sm">
              <li>
                <Link to="/" className="text-white/80 hover:text-white">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/chat" className="text-white/80 hover:text-white">
                  Chat Assistant
                </Link>
              </li>
              <li>
                <a
                  href={PARTSELECT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white/80 hover:text-white"
                >
                  PartSelect.com
                </a>
              </li>
            </ul>
          </div>

          {/* Tech */}
          <div className="md:text-right">
            <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ps-gold md:text-right">
              Built With
            </h4>
            <p className="mt-4 text-sm text-white/80">
              Powered by Gemini AI + LangGraph
            </p>
          </div>
        </div>

        <div className="mt-12 border-t border-white/10 pt-6 text-center text-xs text-white/60">
          © 2026 PartSelect AI Assistant. Built for InstaLILY Case Study.
        </div>
      </div>
    </footer>
  );
};

export default Footer;
