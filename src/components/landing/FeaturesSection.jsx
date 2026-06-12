import React from "react";
import { Search, Wrench, ShieldCheck, PackageSearch } from "lucide-react";

const FEATURES = [
  {
    icon: Search,
    title: "Find Any Part",
    desc: "Enter a part number or describe what you need. Instant results from the full catalog.",
  },
  {
    icon: Wrench,
    title: "Troubleshoot Issues",
    desc: "Describe your problem and get step-by-step guidance. Ice maker? Leaking? We help.",
  },
  {
    icon: ShieldCheck,
    title: "Check Compatibility",
    desc: "Enter your model number once. We verify every part against it automatically.",
  },
  {
    icon: PackageSearch,
    title: "Track Your Order",
    desc: "Check order status and get real-time tracking updates instantly.",
  },
];

const FeaturesSection = () => {
  return (
    <section className="border-t border-ps-border bg-ps-bgAlt py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Capabilities</p>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-ps-text sm:text-4xl">
            Everything You Need to Fix Your Appliance
          </h2>
          <p className="mt-4 text-ps-textMuted">
            One assistant for finding parts, diagnosing problems, confirming fit,
            and tracking your order — all in a single conversation.
          </p>
        </div>

        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="group relative overflow-hidden rounded-2xl border border-ps-border bg-white p-6 shadow-card transition-all hover:-translate-y-1 hover:border-ps-teal/40 hover:shadow-cardHover"
              >
                <span className="absolute inset-x-0 top-0 h-1 origin-left scale-x-0 bg-ps-gold transition-transform duration-300 group-hover:scale-x-100" />
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-ps-tealSoft text-ps-teal">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="mt-4 text-lg font-bold text-ps-text">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ps-textMuted">
                  {f.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
