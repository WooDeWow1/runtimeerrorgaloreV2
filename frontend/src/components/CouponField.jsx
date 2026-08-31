import { useState } from "react";
import { Tag, X } from "lucide-react";
import { useCart } from "@/context/CartContext";
import { money } from "@/lib/api";

export const CouponField = ({ email = "", testPrefix = "cart" }) => {
  const { coupon, couponBusy, applyCoupon, clearCoupon } = useCart();
  const [code, setCode] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    const ok = await applyCoupon(code, email);
    if (ok) setCode("");
  };

  if (coupon)
    return (
      <div
        data-testid={`${testPrefix}-coupon-applied`}
        className="border border-[#00ffcc]/40 bg-[#00ffcc]/[0.06] p-3"
      >
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.15em] text-[#00ffcc]">
            <Tag className="h-3.5 w-3.5" /> {coupon.code} · −{money(coupon.discount)}
          </p>
          <button
            type="button"
            data-testid={`${testPrefix}-remove-coupon-btn`}
            onClick={clearCoupon}
            title="Remove code"
            className="text-zinc-500 transition-colors hover:text-[#ff3b30]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        {coupon.excluded_names?.length > 0 && (
          <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
            Not discounted: {coupon.excluded_names.join(", ")}
          </p>
        )}
      </div>
    );

  return (
    <form onSubmit={submit}>
      <label className="mb-2 block text-[10px] uppercase tracking-[0.2em] text-zinc-500">
        Discount code
      </label>
      <div className="flex gap-2">
        <input
          data-testid={`${testPrefix}-coupon-input`}
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="ENTER CODE"
          className="w-full bg-[#050505] px-3 py-2.5 font-mono text-xs uppercase tracking-[0.15em] text-white outline-none ring-1 ring-zinc-800 transition-shadow placeholder:text-zinc-700 focus:ring-[#00ffcc]"
        />
        <button
          type="submit"
          data-testid={`${testPrefix}-apply-coupon-btn`}
          disabled={couponBusy || !code.trim()}
          className="shrink-0 border border-[#00ffcc] px-4 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent"
        >
          {couponBusy ? "…" : "Apply"}
        </button>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
        Event Passes are excluded — in a mixed cart the discount applies to the eligible items only.
      </p>
    </form>
  );
};
