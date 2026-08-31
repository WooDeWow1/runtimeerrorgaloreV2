import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";

const CartContext = createContext(null);
const KEY = "pokeforge_cart";

const lineKey = (productId, variantId) => `${productId}:${variantId || ""}`;

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(KEY)) || [];
      // Older carts predate variants and have no line key.
      return stored.map((i) => ({ ...i, key: i.key || lineKey(i.id, i.variant_id) }));
    } catch {
      return [];
    }
  });
  const [open, setOpen] = useState(false);
  const [coupon, setCoupon] = useState(null);
  const [couponBusy, setCouponBusy] = useState(false);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(items));
  }, [items]);

  const hasCoins = items.some((i) => i.category === "pokecoin_bundle");
  const hasPass = items.some((i) => i.category === "event_pass");
  const passCount = items
    .filter((i) => i.category === "event_pass")
    .reduce((n, i) => n + i.quantity, 0);
  const hasOther = items.some((i) => i.category !== "event_pass");

  const add = (product, variant = null) => {
    if (product.coming_soon) {
      toast.error(`${product.name} is not released yet.`);
      return false;
    }
    if (product.category === "event_pass") {
      if (!hasOther) {
        toast.error("Event Pass locked", {
          description:
            "Add Pokécoins, Stardust or a Medal bundle first — Event Passes cannot be bought alone.",
        });
        return false;
      }
      if (passCount >= 1) {
        toast.error("One Event Pass per order", {
          description: "Check out this one first, then start a new order for another pass.",
        });
        return false;
      }
    }
    const variantId = variant ? variant.sellauth_variant_id : null;
    const key = lineKey(product.id, variantId);
    setItems((prev) => {
      if (prev.some((i) => i.key === key))
        return prev.map((i) => (i.key === key ? { ...i, quantity: i.quantity + 1 } : i));
      return [
        ...prev,
        {
          key,
          id: product.id,
          name: product.name,
          price: variant ? variant.price : product.price,
          category: product.category,
          image_url: product.image_url,
          variant_id: variantId,
          variant_label: variant ? variant.label : "",
          quantity: 1,
        },
      ];
    });
    toast.success(`${product.name}${variant ? ` (${variant.label})` : ""} added to cart`);
    return true;
  };

  const remove = (key) => setItems((prev) => prev.filter((i) => i.key !== key));
  const setQty = (key, qty) =>
    setItems((prev) =>
      prev.map((i) => {
        if (i.key !== key) return i;
        const cap = i.category === "event_pass" ? 1 : 50;
        return { ...i, quantity: Math.max(1, Math.min(cap, qty)) };
      })
    );
  const clear = () => {
    setItems([]);
    setCoupon(null);
  };

  const cartPayload = useMemo(
    () =>
      items.map((i) => ({
        product_id: i.id,
        quantity: i.quantity,
        ...(i.variant_id ? { variant_id: i.variant_id } : {}),
      })),
    [items]
  );

  const applyCoupon = async (code, email = "") => {
    const trimmed = (code || "").trim().toUpperCase();
    if (!trimmed) return false;
    setCouponBusy(true);
    try {
      const { data } = await api.post("/coupons/validate", {
        code: trimmed,
        items: cartPayload,
        ...(email ? { email } : {}),
      });
      setCoupon(data);
      toast.success(`${data.code} applied — ${data.percent_label} off`);
      return true;
    } catch (err) {
      setCoupon(null);
      toast.error(apiError(err));
      return false;
    } finally {
      setCouponBusy(false);
    }
  };

  const clearCoupon = () => setCoupon(null);

  // The cart changed: re-price the applied code (it may now be invalid, e.g. under the minimum).
  useEffect(() => {
    if (!coupon) return;
    if (items.length === 0) {
      setCoupon(null);
      return;
    }
    let stale = false;
    api
      .post("/coupons/validate", { code: coupon.code, items: cartPayload })
      .then(({ data }) => {
        if (!stale) setCoupon(data);
      })
      .catch((err) => {
        if (stale) return;
        setCoupon(null);
        toast.error(`${coupon.code} removed`, { description: apiError(err) });
      });
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartPayload]);

  const total = useMemo(
    () => items.reduce((sum, i) => sum + i.price * i.quantity, 0),
    [items]
  );
  const discount = coupon ? coupon.discount : 0;
  const payable = coupon ? coupon.total : total;
  const count = items.reduce((sum, i) => sum + i.quantity, 0);
  const invalid = hasPass && !hasOther;

  return (
    <CartContext.Provider
      value={{ items, add, remove, setQty, clear, total, discount, payable, count, invalid,
               hasCoins, hasPass, hasOther, passCount, open, setOpen,
               coupon, couponBusy, applyCoupon, clearCoupon, cartPayload }}
    >
      {children}
    </CartContext.Provider>
  );
}

export const useCart = () => useContext(CartContext);
