import React from "react";
import { MessageSquare, Search, ShoppingCart, ChevronRight } from "lucide-react";

const STEPS = [
  {
    num: "01",
    icon: MessageSquare,
    title: "Describe Your Issue",
    desc: "Tell us what's wrong or what part you need.",
  },
  {
    num: "02",
    icon: Search,
    title: "AI Finds The Part",
    desc: "Our agent searches PartSelect's entire catalog instantly.",
  },
  {
    num: "03",
    icon: ShoppingCart,
    title: "Order with Confidence",
    desc: "Add the right part to cart directly from chat.",
  },
];

const HowItWorksSection = () => {
  return (
    <section className="border-t border-ps-border bg-white py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-ps-text sm:text-4xl">
            Get Help in 3 Simple Steps
          </h2>
        </div>

        <div className="mt-14 grid grid-cols-1 items-stretch gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
          {STEPS.map((s, idx) => {
            const Icon = s.icon;
            return (
              <React.Fragment key={s.num}>
                <div className="relative overflow-hidden rounded-2xl border border-ps-border bg-white p-6 shadow-card">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-2xl font-semibold text-ps-gold">
                      {s.num}
                    </span>
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ps-tealSoft text-ps-teal">
                      <Icon className="h-5 w-5" />
                    </span>
                  </div>
                  <h3 className="mt-5 text-lg font-bold text-ps-text">
                    {s.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-ps-textMuted">
                    {s.desc}
                  </p>
                </div>

                {idx < STEPS.length - 1 && (
                  <div className="flex items-center justify-center text-ps-textFaint">
                    <ChevronRight className="hidden h-6 w-6 md:block" />
                    <div className="my-1 h-5 w-px bg-ps-border md:hidden" />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
