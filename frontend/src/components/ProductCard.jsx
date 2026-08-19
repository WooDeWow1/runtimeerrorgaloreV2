import { useState } from "react";
import { Lock, Plus } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";

export const ProductCard = ({ product, featured = false }) => {
  const { add, hasCoins } = useCart();
  const { user } = useAuth();
  const comingSoon = !!product.coming_soon;
  const locked = !comingSoon && product.category === "event_pass" && !hasCoins;
  const [joining, setJoining] = useState(false);

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
    product.msrp && product.msrp > product.price
      ? Math.round(((product.msrp - product.price) / product.msrp) * 100)
      : null;

  return (
    <motion.article
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
      data-testid={`product-card-${product.id}`}
      className="group relative flex flex-col border border-[#1f1f1f] bg-[#0a0a0a] transition-colors hover:border-[#00ffcc]"
    >
      <div className={`relative overflow-hidden ${featured ? "h-56 sm:h-72" : "h-40"}`}>
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
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h3 className="font-display text-base font-bold leading-tight">{product.name}</h3>
        <p className="mt-2 line-clamp-5 flex-1 text-xs leading-relaxed text-zinc-500">{product.description}</p>

        {product.category === "event_pass" && (
          <span
            data-testid={`requires-bundle-badge-${product.id}`}
            className="mt-4 self-start border border-[#f4d03f]/50 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-[#f4d03f]"
          >
            Requires Coin Bundle
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
            Locked — add a Pokécoin Bundle to your cart to unlock this Event Pass.
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
              {money(product.price)}
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
              onClick={() => add(product)}
              title={locked ? "Requires a Pokécoin Bundle" : "Add to cart"}
              className="flex items-center gap-2 border border-zinc-700 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
            >
              {locked ? <Lock className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
              {locked ? "Locked" : "Add"}
            </button>
          )}
        </div>
      </div>
    </motion.article>
  );
};
