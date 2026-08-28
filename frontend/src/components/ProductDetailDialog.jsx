import { AlertTriangle, Lock, Plus } from "lucide-react";
import { money } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const ProductDetailDialog = ({
  product,
  open,
  onOpenChange,
  variants,
  variantId,
  setVariantId,
  price,
  locked,
  comingSoon,
  onAdd,
  onJoinWaitlist,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent
      data-testid={`product-detail-${product.id}`}
      className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-2xl overflow-y-auto border border-[#1f1f1f] bg-[#0a0a0a] p-0 text-white"
    >
      {product.image_url && (
        <img src={product.image_url} alt={product.name} className="h-44 w-full object-cover sm:h-56" />
      )}
      <div className="px-6 pb-6">
        <DialogHeader className="text-left">
          <DialogTitle className="font-display text-xl leading-tight tracking-tight sm:text-2xl">
            {product.name}
          </DialogTitle>
          <DialogDescription className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
            Full product details
          </DialogDescription>
        </DialogHeader>

        <p
          data-testid={`product-detail-description-${product.id}`}
          className="mt-4 whitespace-pre-line text-sm leading-relaxed text-zinc-300"
        >
          {product.description}
        </p>

        {product.category === "event_pass" && (
          <div className="mt-5 flex gap-3 border border-[#f4d03f]/50 bg-[#f4d03f]/10 p-4 text-xs leading-relaxed text-[#f4d03f]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              Add-on only — an Event Pass must be bought alongside another product, one per order.
            </span>
          </div>
        )}

        {variants.length > 0 && !comingSoon && (
          <div className="mt-6">
            <label className="mb-2 block text-[10px] uppercase tracking-[0.2em] text-zinc-500">
              Option
            </label>
            <select
              data-testid={`detail-variant-select-${product.id}`}
              value={variantId}
              onChange={(e) => setVariantId(e.target.value)}
              className="w-full bg-[#050505] px-3 py-3 text-sm text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
            >
              {variants.map((v) => (
                <option key={v.sellauth_variant_id} value={v.sellauth_variant_id}>
                  {`${v.label} — ${money(v.price)}`}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-zinc-800 pt-5">
          <span
            data-testid={`detail-price-${product.id}`}
            className={`font-display text-2xl ${comingSoon ? "text-zinc-500" : "text-[#00ffcc]"}`}
          >
            {money(price)}
          </span>
          {comingSoon ? (
            <button
              data-testid={`detail-join-waitlist-${product.id}`}
              onClick={onJoinWaitlist}
              className="border border-[#9966cc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#9966cc] transition-colors hover:bg-[#9966cc] hover:text-black"
            >
              Join Waitlist
            </button>
          ) : (
            <button
              data-testid={`detail-add-to-cart-${product.id}`}
              onClick={() => {
                if (onAdd()) onOpenChange(false);
              }}
              className="flex items-center gap-2 border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
            >
              {locked ? <Lock className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
              {locked ? "Locked" : "Add to cart"}
            </button>
          )}
        </div>
      </div>
    </DialogContent>
  </Dialog>
);
