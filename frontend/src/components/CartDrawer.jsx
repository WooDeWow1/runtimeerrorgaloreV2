import { useNavigate } from "react-router-dom";
import { AlertTriangle, Minus, Plus, Trash2 } from "lucide-react";
import { useCart } from "@/context/CartContext";
import { money } from "@/lib/api";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

export const CartDrawer = () => {
  const { items, remove, setQty, total, invalid, open, setOpen } = useCart();
  const navigate = useNavigate();

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent
        data-testid="cart-drawer"
        className="flex w-full flex-col border-l border-zinc-800 bg-[#070707] p-0 sm:max-w-md"
      >
        <SheetHeader className="border-b border-zinc-800 px-6 py-5 text-left">
          <SheetTitle className="font-display text-sm uppercase tracking-[0.25em] text-white">
            Your Cart
          </SheetTitle>
          <SheetDescription className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
            Event Passes require a Pokécoin Bundle
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {items.length === 0 && (
            <p data-testid="cart-empty" className="text-xs text-zinc-500">
              Cart is empty. Load up on Pokécoins.
            </p>
          )}
          <div className="space-y-4">
            {items.map((i) => (
              <div key={i.id} data-testid={`cart-item-${i.id}`} className="flex gap-4 border border-zinc-900 p-3">
                {i.image_url && (
                  <img src={i.image_url} alt={i.name} className="h-16 w-16 object-cover" />
                )}
                <div className="flex-1">
                  <p className="text-xs font-bold text-white">{i.name}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                    {money(i.price)}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      data-testid={`cart-dec-${i.id}`}
                      onClick={() => setQty(i.id, i.quantity - 1)}
                      className="border border-zinc-800 p-1 text-zinc-400 hover:text-[#00ffcc]"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                    <span data-testid={`cart-qty-${i.id}`} className="w-6 text-center text-xs">{i.quantity}</span>
                    <button
                      data-testid={`cart-inc-${i.id}`}
                      onClick={() => setQty(i.id, i.quantity + 1)}
                      className="border border-zinc-800 p-1 text-zinc-400 hover:text-[#00ffcc]"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                    <button
                      data-testid={`cart-remove-${i.id}`}
                      onClick={() => remove(i.id)}
                      className="ml-auto text-zinc-500 hover:text-[#ff3b30]"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {invalid && (
            <div
              data-testid="cart-validation-error"
              className="mt-5 flex gap-3 border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-xs text-[#ff3b30]"
            >
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>
                Event Passes cannot be purchased alone. Add Pokécoins, Stardust or a Medal bundle to
                unlock checkout.
              </span>
            </div>
          )}
        </div>

        <div className="border-t border-zinc-800 px-6 py-5">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-zinc-400">
            <span>Total</span>
            <span data-testid="cart-total" className="font-display text-lg text-white">{money(total)}</span>
          </div>
          <button
            data-testid="checkout-btn"
            disabled={items.length === 0 || invalid}
            onClick={() => {
              setOpen(false);
              navigate("/checkout");
            }}
            className="mt-4 w-full border border-[#00ffcc] py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:cursor-not-allowed disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent"
          >
            Proceed to checkout
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
};
