import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

const CTASection = () => {
  return (
    <section className="bg-white py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ps-teal to-ps-tealDeep px-6 py-16 text-center">
          {/* Subtle decorative washes */}
          <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/5 blur-2xl" />
          <div className="pointer-events-none absolute -bottom-24 left-1/4 h-72 w-72 rounded-full bg-ps-gold/10 blur-3xl" />
          <div className="relative">
            <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
              Ready to Fix Your Appliance?
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-white/85">
              Get instant help from our AI assistant — available 24/7
            </p>
            <Link
              to="/chat"
              className="group mt-8 inline-flex items-center gap-1.5 rounded-lg bg-ps-gold px-8 py-4 text-base font-bold text-ps-text shadow-goldGlow transition-all hover:-translate-y-0.5 hover:bg-ps-goldDark"
            >
              Start Chatting Now
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTASection;
