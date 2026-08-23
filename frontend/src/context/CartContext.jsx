import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

const CartContext = createContext(null);
const KEY = "pokeforge_cart";

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || [];
    } catch {
      return [];
    }
  });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(items));
  }, [items]);

  const hasCoins = items.some((i) => i.category === "pokecoin_bundle");
  const hasPass = items.some((i) => i.category === "event_pass");
  const passCount = items
    .filter((i) => i.category === "event_pass")
    .reduce((n, i) => n + i.quantity, 0);
  const hasOther = items.some((i) => i.category !== "event_pass");

  const add = (product) => {
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
    setItems((prev) => {
      const found = prev.find((i) => i.id === product.id);
      if (found) return prev.map((i) => (i.id === product.id ? { ...i, quantity: i.quantity + 1 } : i));
      return [
        ...prev,
        {
          id: product.id,
          name: product.name,
          price: product.price,
          category: product.category,
          image_url: product.image_url,
          quantity: 1,
        },
      ];
    });
    toast.success(`${product.name} added to cart`);
    return true;
  };

  const remove = (id) => setItems((prev) => prev.filter((i) => i.id !== id));
  const setQty = (id, qty) =>
    setItems((prev) =>
      prev.map((i) => {
        if (i.id !== id) return i;
        const cap = i.category === "event_pass" ? 1 : 50;
        return { ...i, quantity: Math.max(1, Math.min(cap, qty)) };
      })
    );
  const clear = () => setItems([]);

  const total = useMemo(
    () => items.reduce((sum, i) => sum + i.price * i.quantity, 0),
    [items]
  );
  const count = items.reduce((sum, i) => sum + i.quantity, 0);
  const invalid = hasPass && !hasOther;

  return (
    <CartContext.Provider
      value={{ items, add, remove, setQty, clear, total, count, invalid, hasCoins, hasPass,
               hasOther, passCount, open, setOpen }}
    >
      {children}
    </CartContext.Provider>
  );
}

export const useCart = () => useContext(CartContext);
