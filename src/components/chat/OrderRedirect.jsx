import React from "react";
import { ExternalLink, Package, ShoppingCart, RotateCcw } from "lucide-react";

// Renders a clean redirect button for order-related intents. Orders, order
// status, and returns are handled on the real PartSelect site — never scraped
// or transacted through the agent.
const REDIRECTS = {
  order_status_redirect: { label: "Check Order Status", Icon: Package },
  returns_redirect: { label: "Start a Return", Icon: RotateCcw },
};

const OrderRedirect = ({ type, url }) => {
  if (!url) return null;

  const { label, Icon } = REDIRECTS[type] || {
    label: "Order on PartSelect",
    Icon: ShoppingCart,
  };

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 rounded-xl bg-ps-teal px-4 py-2.5 text-sm font-semibold text-white shadow-card transition-colors hover:bg-ps-tealDark"
    >
      <Icon className="h-4 w-4" />
      {label}
      <ExternalLink className="h-3.5 w-3.5 opacity-80" />
    </a>
  );
};

export default OrderRedirect;
