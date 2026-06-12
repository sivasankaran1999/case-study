import React, { useState } from "react";
import {
  ImageOff,
  ExternalLink,
  ShoppingCart,
  Wrench,
  Package,
  CheckCircle2,
  PlayCircle,
} from "lucide-react";
import CompatibilityBadge from "./CompatibilityBadge";

const formatPrice = (price) => {
  if (price === null || price === undefined || isNaN(Number(price))) return null;
  return `$${Number(price).toFixed(2)}`;
};

// Pull the 11-char YouTube id out of any embed/watch/short URL so we can build
// a thumbnail and a privacy-friendly (no-cookie) embed.
const youTubeId = (url) => {
  if (!url) return "";
  const m = String(url).match(
    /(?:youtube(?:-nocookie)?\.com\/(?:embed\/|watch\?v=)|youtu\.be\/)([A-Za-z0-9_-]{11})/
  );
  return m ? m[1] : "";
};

const DetailRow = ({ label, children }) => {
  if (!children) return null;
  return (
    <div className="flex gap-3 border-b border-ps-border/60 py-2.5 last:border-0 last:pb-0">
      <span className="w-[5.5rem] shrink-0 text-xs font-semibold uppercase tracking-wide text-ps-text">
        {label}
      </span>
      <div className="min-w-0 flex-1 text-sm leading-relaxed text-ps-textMuted">
        {children}
      </div>
    </div>
  );
};

const PartCard = ({ part, modelNumber, compact = false }) => {
  const [imgFailed, setImgFailed] = useState(false);
  const [showVideo, setShowVideo] = useState(false);

  if (!part) return null;

  const {
    part_number,
    name,
    price,
    in_stock,
    availability,
    image_url,
    product_url,
    compatible_with = [],
    description,
    fixes_symptoms = [],
    installation_steps = [],
    video_url,
    fits_model,
  } = part;

  const videoId = youTubeId(video_url);

  const compatList = Array.isArray(compatible_with) ? compatible_with : [];
  // Compatibility is a CONFIRM-only signal. The authoritative source is the
  // backend `fits_model` flag (derived from the model's full parts list). The
  // part's own `compatible_with` list is scraped and often truncated, so its
  // ABSENCE is not evidence of incompatibility — we must never render a hard
  // "not compatible" from it (that produced false negatives that contradicted
  // the clarify-list badge). So: green when confirmed, neutral "verify"
  // otherwise, and nothing when no model is known.
  const confirmedFit =
    fits_model === true ||
    (!!modelNumber &&
      compatList.some(
        (m) => String(m).toUpperCase() === modelNumber.toUpperCase()
      ));
  const showVerifyFit = !confirmedFit && !!modelNumber;

  const priceLabel = formatPrice(price);
  const showImage = image_url && !imgFailed;

  // Availability is richer than a boolean: a part can be orderable on Special
  // Order (longer lead time) — not "Out of Stock". Prefer the backend label and
  // fall back to the in_stock flag for older payloads.
  const stockLabel = availability || (in_stock ? "In Stock" : "Out of Stock");
  const isSpecialOrder = /special order/i.test(stockLabel);
  const orderable =
    typeof availability === "string" && availability
      ? !/out of stock|discontinued|no longer/i.test(availability)
      : in_stock;
  const stockTone = isSpecialOrder ? "warn" : orderable ? "success" : "error";
  const hasStockInfo =
    (typeof availability === "string" && availability) ||
    typeof in_stock === "boolean";

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-ps-border bg-white shadow-card ${
        compact ? "w-60 shrink-0" : "w-full"
      }`}
    >
      <div className="flex h-48 items-center justify-center bg-gradient-to-b from-white to-ps-bgAlt px-6 py-4">
        {showImage ? (
          <img
            src={image_url}
            alt={name || "Part image"}
            onError={() => setImgFailed(true)}
            className="max-h-full max-w-full object-contain drop-shadow-md"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-ps-textFaint">
            <ImageOff className="h-10 w-10" />
            <span className="text-xs">No image available</span>
          </div>
        )}
      </div>

      <div className="border-t border-ps-border">
        <div className="bg-ps-bgAlt/50 px-4 py-3">
          <h4 className="text-base font-bold leading-snug text-ps-text">
            {name || "Replacement Part"}
          </h4>
          {part_number && (
            <p className="mt-0.5 font-mono text-xs font-medium text-ps-teal">
              {part_number}
            </p>
          )}
        </div>

        <div className="px-4 py-1">
          <DetailRow label="About">
            {description || "Genuine OEM replacement part from PartSelect."}
          </DetailRow>

          {fixes_symptoms.length > 0 && (
            <DetailRow label="Fixes">
              <ul className="space-y-1">
                {fixes_symptoms.slice(0, 4).map((s) => (
                  <li key={s} className="flex items-start gap-1.5">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ps-success" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </DetailRow>
          )}

          {installation_steps.length > 0 && (
            <DetailRow label="Install">
              {installation_steps.length === 1 ? (
                <span className="flex items-start gap-1.5">
                  <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ps-teal" />
                  {installation_steps[0]}
                </span>
              ) : (
                <ol className="list-decimal space-y-1 pl-4">
                  {installation_steps.slice(0, 5).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              )}
            </DetailRow>
          )}

          <DetailRow label="Fits">
            {compatList.length > 0 ? (
              <span>
                {compatList.slice(0, 4).join(", ")}
                {compatList.length > 4 && ` +${compatList.length - 4} more`}
              </span>
            ) : (
              "Verify your model number on PartSelect before ordering."
            )}
          </DetailRow>
        </div>

        {videoId && (
          <div className="border-t border-ps-border px-4 py-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ps-text">
              <PlayCircle className="h-4 w-4 text-ps-teal" />
              Installation Video
            </div>
            {showVideo ? (
              <div className="relative w-full overflow-hidden rounded-xl bg-black pb-[56.25%]">
                <iframe
                  className="absolute inset-0 h-full w-full"
                  src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0`}
                  title="Part installation video"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowVideo(true)}
                aria-label="Play installation video"
                className="group relative block w-full overflow-hidden rounded-xl bg-black pb-[56.25%]"
              >
                <img
                  src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`}
                  alt="Installation video thumbnail"
                  className="absolute inset-0 h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
                />
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-full bg-black/55 transition-colors group-hover:bg-ps-teal">
                    <PlayCircle className="h-9 w-9 text-white" />
                  </span>
                </span>
              </button>
            )}
            <p className="mt-1.5 text-xs text-ps-textMuted">
              Step-by-step replacement guide for this part.
            </p>
          </div>
        )}

        <div className="border-t border-ps-border bg-ps-bgAlt/30 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {priceLabel && (
              <span className="font-mono text-xl font-extrabold tracking-tight text-ps-text">
                {priceLabel}
              </span>
            )}
            {hasStockInfo && (
              <CompatibilityBadge tone={stockTone}>
                {stockLabel}
              </CompatibilityBadge>
            )}
            {orderable && (
              <span className="inline-flex items-center gap-1 text-xs text-ps-textMuted">
                <Package className="h-3.5 w-3.5" />
                {isSpecialOrder
                  ? "Orderable — longer lead time"
                  : "Ships within 1 business day"}
              </span>
            )}
          </div>

          {confirmedFit && (
            <div className="mt-2">
              <CompatibilityBadge ok={true}>
                {`Compatible with ${modelNumber}`}
              </CompatibilityBadge>
            </div>
          )}
          {showVerifyFit && (
            <div className="mt-2">
              <a
                href={product_url || "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-ps-border bg-white px-2.5 py-1 text-xs font-medium text-ps-textMuted transition-colors hover:border-ps-teal/50 hover:text-ps-teal"
              >
                <ExternalLink className="h-3 w-3" />
                {`Verify fit for ${modelNumber} on PartSelect`}
              </a>
            </div>
          )}

          <div className="mt-3 flex gap-2">
            <a
              href={product_url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-ps-teal/30 bg-white px-3 py-2.5 text-center text-xs font-semibold text-ps-teal transition-colors hover:border-ps-teal/50 hover:bg-ps-tealSoft"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View Part
            </a>
            <a
              href={product_url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-ps-gold px-3 py-2.5 text-center text-xs font-bold text-ps-text shadow-sm transition-colors hover:bg-ps-goldDark"
            >
              <ShoppingCart className="h-3.5 w-3.5" />
              Add to Cart
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PartCard;
