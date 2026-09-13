import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, Mail } from "lucide-react";
import { api } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";
import { OrderChat } from "@/components/OrderChat";
import { ClaimAccountCard } from "@/components/ClaimAccountCard";

export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id") || localStorage.getItem("pokeforge_checkout_session");
  const payUrl = localStorage.getItem("pokeforge_checkout_url");
  const [state, setState] = useState("checking");
  const [orderId, setOrderId] = useState(null);
  const [orderKey, setOrderKey] = useState("");
  const [orderEmail, setOrderEmail] = useState("");
  const { clear } = useCart();
  const { user } = useAuth();
  const cleared = useRef(false);
  // Kept in a ref so clearing the cart never restarts the payment poll.
  const clearCart = useRef(clear);
  clearCart.current = clear;

  useEffect(() => {
    if (!orderId) return;
    api
      .get(`/orders/${orderId}`, { params: orderKey ? { k: orderKey } : {} })
      .then(({ data }) => setOrderEmail(data.user_email || ""))
      .catch(() => {});
  }, [orderId, orderKey]);

  useEffect(() => {
    if (!sessionId) {
      setState("pending");
      return;
    }
    let attempts = 0;
    let timer;
    const poll = async () => {
      attempts += 1;
      try {
        const { data } = await api.get(`/checkout-sessions/${sessionId}`);
        if (data.order_id) {
          setOrderId(data.order_id);
          setOrderKey(data.order_key || "");
          setState("paid");
          if (!cleared.current) {
            cleared.current = true;
            clearCart.current();
            localStorage.removeItem("pokeforge_checkout_url");
            localStorage.setItem(
              "pokeforge_guest_orders",
              JSON.stringify([
                data.order_id,
                ...JSON.parse(localStorage.getItem("pokeforge_guest_orders") || "[]").filter(
                  (id) => id !== data.order_id
                ),
              ])
            );
          }
          return;
        }
      } catch {
        setState("pending");
        return;
      }
      if (attempts >= 60) {
        setState("pending");
        return;
      }
      timer = setTimeout(poll, 2000);
    };
    poll();
    return () => clearTimeout(timer);
  }, [sessionId]);

  return (
    <div data-testid="payment-success-page" className="mx-auto max-w-xl px-5 py-24 text-center">
      {state === "checking" && (
        <>
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-[#00ffcc]" />
          <h1 className="mt-6 font-display text-2xl tracking-tighter">Waiting for payment confirmation…</h1>
          <p className="mt-4 text-xs text-zinc-500">
            Finish paying in the tab we just opened. Crypto and Cash App payments can take a couple of
            minutes to settle — keep this page open and it will confirm itself.
          </p>
          {payUrl && (
            <a
              href={payUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="reopen-payment-btn"
              className="mt-8 inline-block border border-[#00ffcc] px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
            >
              Reopen payment window
            </a>
          )}
        </>
      )}
      {state === "paid" && (
        <>
          <CheckCircle2 className="mx-auto h-10 w-10 text-[#00ffcc]" />
          <h1 data-testid="payment-paid-heading" className="mt-6 font-display text-2xl tracking-tighter">
            Payment confirmed
          </h1>
          <p className="mt-4 text-xs leading-relaxed text-zinc-400">
            Your order is queued and the tracking link is on its way to your inbox. You'll see the status
            change to Processing when an operator logs in — stay logged out then.
          </p>
          <Link
            to={`/order/${orderId}${orderKey ? `?k=${orderKey}` : ""}`}
            data-testid="view-order-btn"
            className="mt-8 inline-block border border-[#00ffcc] px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black"
          >
            Track order
          </Link>

          <div className="mt-12 text-left">
            <h2 className="mb-4 text-[11px] uppercase tracking-[0.25em] text-zinc-300">
              Chat with support
            </h2>
            <OrderChat orderId={orderId} accessKey={orderKey} />
          </div>

          {!user && <ClaimAccountCard orderId={orderId} email={orderEmail} accessKey={orderKey} />}
        </>
      )}
      {state === "pending" && (
        <>
          <Mail className="mx-auto h-10 w-10 text-[#f4d03f]" />
          <h1 className="mt-6 font-display text-2xl tracking-tighter">Payment still settling</h1>
          <p data-testid="payment-pending-note" className="mt-4 text-xs leading-relaxed text-zinc-400">
            As soon as SellAuth confirms your payment we create the order and email you a private tracking
            link. Nothing else is needed from you — you can close this page.
          </p>
          <Link
            to="/my-orders"
            className="mt-8 inline-block border border-zinc-700 px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-zinc-300 hover:border-white hover:text-white"
          >
            My orders
          </Link>
        </>
      )}
    </div>
  );
}
