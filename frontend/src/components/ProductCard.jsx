import { useState } from "react";
import { Lock, Plus } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";
import { ProductDetailDialog } from "@/components/ProductDetailDialog";

export const ProductCard = ({ product }) => {
  const { add, hasOther, passCount } = useCart();
  const { user } = useAuth();
  const comingSoon = !!product.coming_soon;
  const locked =
    !comingSoon && product.category === "event_pass" && (!hasOther || passCount >= 1);
  const [joining, setJoining] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const variants = product.variants || [];
  const [variantId, setVariantId] = useState(
    variants.length ? String(variants[0].sellauth_variant_id) : ""
  );
  const variant = variants.find((v) => String(v.sellauth_variant_id) === variantId) || null;
  const price = variant ? variant.price : product.price;

  const joinWaitlist = async () => {
    const email = user?.email || window.prompt("Email for waitlist access:");
    if (!email) return;
    setJoining(true);
    try {
      await api.post("/waitlist", { email, product_id: product.id });
      toast.success("You're on the waitlist", {
        description: `We'll email ${email} the moment ${product.name} opens.`,
      });
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setJoining(false);
    }
  };

  const savings =
    product.msrp && product.msrp > price
      ? Math.round(((product.msrp - price) / product.msrp) * 100)
      : null;

  return (
    <>
      <motion.article
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        data-testid={`product-card-${product.id}`}
        className="group relative flex flex-col border border-[#1f1f1f] bg-[#0a0a0a] transition-colors hover:border-[#00ffcc]"
      >
        <button
          type="button"
          data-testid={`open-details-${product.id}`}
          onClick={() => setDetailOpen(true)}
          title="View full details"
          className="relative block h-40 w-full overflow-hidden text-left"
        >
          <img
            src={product.image_url}
            alt={product.name}
            className="h-full w-full object-cover opacity-80 transition-transform duration-500 group-hover:scale-105"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-transparent to-transparent" />
          {comingSoon && (
            <div
              data-testid={`coming-soon-overlay-${product.id}`}
              className="absolute inset-0 flex items-center justify-center bg-black/65 backdrop-blur-[2px]"
            >
              <span className="border border-[#9966cc] bg-black/70 px-4 py-2 text-[10px] font-bold uppercase tracking-[0.3em] text-[#c7a6f0]">
                Coming Soon
              </span>
            </div>
          )}
          {product.badge && !comingSoon && (
            <span className="absolute left-3 top-3 border border-[#00ffcc]/60 bg-black/70 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-[#00ffcc]">
              {product.badge}
            </span>
          )}
          {savings && !comingSoon && (
            <span
              data-testid={`product-savings-${product.id}`}
              className="absolute right-3 top-3 bg-[#00ffcc] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-black"
            >
              -{savings}%
            </span>
          )}
        </button>

        <div className="flex flex-1 flex-col p-5">
          <button
            type="button"
            onClick={() => setDetailOpen(true)}
            className="text-left font-display text-base font-bold leading-tight hover:text-[#00ffcc]"
          >
            {product.name}
          </button>
          <p className="mt-2 line-clamp-3 flex-1 whitespace-pre-line text-xs leading-relaxed text-zinc-500">
            {product.description}
          </p>
          <button
            type="button"
            data-testid={`read-more-${product.id}`}
            onClick={() => setDetailOpen(true)}
            className="mt-2 self-start text-[10px] uppercase tracking-[0.2em] text-[#00ffcc] hover:underline"
          >
            Full details
          </button>

          {variants.length > 0 && !comingSoon && (
            <div className="mt-4">
              <label className="mb-1.5 block text-[9px] uppercase tracking-[0.2em] text-zinc-500">
                Option
              </label>
              <select
                data-testid={`variant-select-${product.id}`}
                value={variantId}
                onChange={(e) => setVariantId(e.target.value)}
                className="w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
              >
                {variants.map((v) => (
                  <option key={v.sellauth_variant_id} value={v.sellauth_variant_id}>
                    {`${v.label} — ${money(v.price)}${v.badge ? ` · ${v.badge}` : ""}`}
                  </option>
                ))}
              </select>
            </div>
          )}

          {product.category === "event_pass" && (
            <span
              data-testid={`requires-bundle-badge-${product.id}`}
              className="mt-4 self-start border border-[#f4d03f]/50 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-[#f4d03f]"
            >
              Add-on only · 1 per order
            </span>
          )}
          {product.category === "medals" && (
            <span
              data-testid={`standalone-badge-${product.id}`}
              className="mt-4 self-start border border-[#9966cc]/50 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-[#c7a6f0]"
            >
              Standalone or bundled
            </span>
          )}

          {comingSoon && (
            <p
              data-testid={`coming-soon-notice-${product.id}`}
              className="mt-4 border border-[#9966cc]/50 bg-[#9966cc]/10 p-3 text-[10px] leading-relaxed text-[#c7a6f0]"
            >
              Coming soon — not purchasable yet. Join the waitlist and we'll email you the moment it opens.
            </p>
          )}

          {locked && (
            <p
              data-testid={`locked-notice-${product.id}`}
              className="mt-4 border border-[#f4d03f]/50 bg-[#f4d03f]/10 p-3 text-[10px] leading-relaxed text-[#f4d03f]"
            >
              Locked — add Pokécoins, Stardust or a Medal bundle to your cart to unlock this Event
              Pass. One pass per order.
            </p>
          )}

          <div className="mt-5 flex items-end justify-between gap-3">
            <div>
              {product.msrp && (
                <p
                  data-testid={`product-msrp-${product.id}`}
                  className="text-[10px] uppercase tracking-[0.2em] text-zinc-600 line-through"
                >
                  MSRP {money(product.msrp)}
                </p>
              )}
              <span
                data-testid={`product-price-${product.id}`}
                className={`font-display text-xl ${comingSoon ? "text-zinc-500" : "text-[#00ffcc]"}`}
              >
                {money(price)}
              </span>
            </div>
            {comingSoon ? (
              <button
                data-testid={`join-waitlist-${product.id}`}
                onClick={joinWaitlist}
                disabled={joining}
                className="border border-[#9966cc] px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-[#9966cc] transition-colors hover:bg-[#9966cc] hover:text-black disabled:opacity-50"
              >
                {joining ? "Adding…" : "Join Waitlist"}
              </button>
            ) : (
              <button
                data-testid={`add-to-cart-${product.id}`}
                onClick={() => add(product, variant)}
                title={locked ? "Add another product first — one pass per order" : "Add to cart"}
                className="flex items-center gap-2 border border-zinc-700 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
              >
                {locked ? <Lock className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                {locked ? "Locked" : "Add"}
              </button>
            )}
          </div>
        </div>
      </motion.article>

      <ProductDetailDialog
        product={product}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        variants={variants}
        variantId={variantId}
        setVariantId={setVariantId}
        variant={variant}
        price={price}
        locked={locked}
        comingSoon={comingSoon}
        onAdd={() => add(product, variant)}
        onJoinWaitlist={joinWaitlist}
      />
    </>
  );
};
