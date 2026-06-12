import React from "react";
import { brands } from "../../styles/theme";

// One brand "logo" wordmark. We don't ship trademarked logo images, so each
// brand is rendered as a clean grayscale wordmark that colorizes on hover —
// the same visual rhythm as a logo wall.
const BrandMark = ({ name }) => (
  <span className="mx-3 inline-flex shrink-0 items-center whitespace-nowrap rounded-xl border border-ps-border bg-white px-7 py-3.5 text-lg font-bold tracking-tight text-ps-textMuted shadow-sm grayscale transition-all duration-300 hover:border-ps-teal/40 hover:text-ps-teal hover:grayscale-0">
    {name}
  </span>
);

const BrandsSection = () => {
  // Duplicate the list so the -50% translate loops seamlessly.
  const track = [...brands, ...brands];

  return (
    <section className="border-t border-ps-border bg-ps-bgAlt py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Coverage</p>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-ps-text sm:text-4xl">
            Works With All Major Brands
          </h2>
        </div>
      </div>

      {/* Edge-faded, full-bleed marquee. `group` lets us pause on hover. */}
      <div className="group relative mt-14 overflow-hidden">
        {/* Left / right fade so logos dissolve into the background at the edges */}
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-ps-bgAlt to-transparent sm:w-40" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-ps-bgAlt to-transparent sm:w-40" />

        <div className="flex w-max animate-marquee items-center group-hover:[animation-play-state:paused] motion-reduce:animate-none">
          {track.map((brand, idx) => (
            <BrandMark key={`${brand}-${idx}`} name={brand} />
          ))}
        </div>
      </div>

      <p className="mt-12 text-center text-sm font-medium text-ps-textFaint">
        And many more…
      </p>
    </section>
  );
};

export default BrandsSection;
