import React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Wrench,
  CheckCircle2,
  ShoppingCart,
  ArrowUp,
  Sparkles,
} from "lucide-react";
import { PARTSELECT_URL } from "../../styles/theme";

// A static, decorative preview of the chat experience used in the hero.
const ChatPreview = () => (
  <div className="relative mx-auto w-full max-w-md">
    <div className="absolute -inset-6 rounded-[2rem] bg-ps-tealGlow blur-3xl" />
    <div className="relative overflow-hidden rounded-2xl border border-ps-border bg-white shadow-cardHover">
      {/* Window header */}
      <div className="flex items-center gap-2.5 border-b border-ps-border bg-ps-bgAlt px-4 py-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ps-tealSoft text-ps-teal">
          <Wrench className="h-4 w-4" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-ps-text">PartSelect AI</p>
          <p className="flex items-center gap-1.5 text-[11px] text-ps-textMuted">
            <span className="h-1.5 w-1.5 rounded-full bg-ps-success" /> Online
          </p>
        </div>
      </div>

      {/* Conversation */}
      <div className="space-y-3 px-4 py-5">
        <div className="max-w-[82%] rounded-2xl rounded-tl-sm border border-ps-border bg-ps-bgAlt px-3 py-2 text-sm text-ps-text">
          My ice maker stopped working. Can you help?
        </div>
        <div className="ml-auto max-w-[82%] rounded-2xl rounded-tr-sm bg-ps-teal px-3 py-2 text-sm font-medium text-white">
          Sure — let's check the water inlet valve first. Here's the likely
          part:
        </div>

        {/* Mini part card */}
        <div className="rounded-xl border border-ps-border bg-white p-3 shadow-card">
          <div className="flex gap-3">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border border-ps-border bg-ps-bgAlt">
              <Wrench className="h-6 w-6 text-ps-textFaint" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ps-text">
                Water Inlet Valve
              </p>
              <p className="font-mono text-xs text-ps-textMuted">PS11752778</p>
              <div className="mt-1 flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-ps-text">
                  $47.99
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-ps-success/10 px-2 py-0.5 text-[10px] font-semibold text-ps-success">
                  <CheckCircle2 className="h-3 w-3" /> In Stock
                </span>
              </div>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <span className="flex-1 rounded-lg border border-ps-teal/40 px-2 py-1.5 text-center text-xs font-semibold text-ps-teal">
              View Part
            </span>
            <span className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-ps-gold px-2 py-1.5 text-center text-xs font-bold text-ps-text">
              <ShoppingCart className="h-3.5 w-3.5" /> Add to Cart
            </span>
          </div>
        </div>
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 border-t border-ps-border px-4 py-3">
        <div className="flex-1 rounded-full border border-ps-border bg-ps-bgAlt px-3 py-2 text-xs text-ps-textFaint">
          Ask about parts, repairs, or compatibility...
        </div>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ps-teal text-white">
          <ArrowUp className="h-4 w-4" />
        </span>
      </div>
    </div>
  </div>
);

const HeroSection = () => {
  return (
    <section className="relative overflow-hidden bg-white">
      {/* Ambient background: faint brand grid + soft green/gold washes */}
      <div className="pointer-events-none absolute inset-0 bg-grid-faint [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_65%)]" />
      <div className="pointer-events-none absolute -top-32 left-1/4 h-80 w-[34rem] -translate-x-1/2 rounded-full bg-ps-tealGlow blur-[120px]" />
      <div className="pointer-events-none absolute -top-24 right-0 h-72 w-[28rem] rounded-full bg-ps-goldSoft/60 blur-[120px]" />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:gap-8 lg:px-8 lg:py-28">
        <div className="text-center lg:text-left">
          <span className="inline-flex items-center gap-2 rounded-full border border-ps-border bg-white px-3 py-1 text-xs font-semibold text-ps-teal shadow-sm">
            <Sparkles className="h-3.5 w-3.5 text-ps-gold" />
            AI assistant for appliance parts
          </span>

          <h1 className="mt-5 text-4xl font-extrabold leading-[1.05] tracking-tight text-ps-text sm:text-5xl lg:text-6xl">
            Find the Right Part.
            <br />
            <span className="relative text-ps-teal">
              Fix It Faster.
              <span className="absolute -bottom-1 left-0 h-1.5 w-full rounded-full bg-ps-gold/70 lg:w-[92%]" />
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-xl text-lg text-ps-textMuted lg:mx-0">
            AI-powered chat assistant for Refrigerator and Dishwasher parts. Get
            instant answers, troubleshooting help, and compatibility checks.
          </p>

          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row lg:justify-start">
            <Link
              to="/chat"
              className="group inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-ps-teal px-6 py-3 text-base font-semibold text-white shadow-glow transition-colors hover:bg-ps-tealDark sm:w-auto"
            >
              Chat with AI Assistant
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <a
              href={PARTSELECT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex w-full items-center justify-center rounded-lg border border-ps-borderStrong bg-white px-6 py-3 text-base font-semibold text-ps-text transition-colors hover:border-ps-teal hover:text-ps-teal sm:w-auto"
            >
              Browse Parts
            </a>
          </div>
        </div>

        <div className="lg:pl-8">
          <ChatPreview />
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
