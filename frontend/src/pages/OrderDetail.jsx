import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { api, apiError, money, STATUS_LABELS } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";

const STEPS = ["pending", "processing", "completed"];

export default function OrderDetail() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      api
        .get(`/orders/${id}`)
        .then(({ data }) => setOrder(data))
        .catch((e) => setError(apiError(e)));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [id]);

  if (error)
    return <div data-testid="order-error" className="mx-auto max-w-xl px-5 py-24 text-xs text-[#ff3b30]">{error}</div>;
  if (!order) return <div className="px-5 py-24 text-center text-xs text-zinc-500">Loading…</div>;

  const stepIndex = STEPS.indexOf(order.status);

  return (
    <div data-testid="order-detail-page" className="mx-auto grid max-w-[1200px] gap-12 px-5 py-16 lg:grid-cols-12 lg:px-10 lg:py-24">
      <div className="lg:col-span-7">
        <Link to="/my-orders" className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 hover:text-[#00ffcc]">
          ← Back to orders
        </Link>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <h1 className="font-display text-2xl tracking-tighter">Order #{order.id.slice(-8)}</h1>
          <StatusBadge status={order.status} testId="order-detail-status" />
        </div>

        <div className="mt-10 flex gap-2">
          {STEPS.map((s, idx) => (
            <div key={s} className="flex-1">
              <div className={`h-1 ${idx <= stepIndex ? "bg-[#00ffcc]" : "bg-zinc-800"}`} />
              <p className={`mt-3 text-[9px] uppercase tracking-[0.2em] ${idx <= stepIndex ? "text-[#00ffcc]" : "text-zinc-600"}`}>
                {STATUS_LABELS[s]}
              </p>
            </div>
          ))}
        </div>

        {order.status === "processing" && (
          <div data-testid="processing-warning" className="mt-8 flex gap-3 border border-[#9966cc] bg-[#9966cc]/10 p-4 text-xs leading-relaxed text-[#c7a6f0]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            An operator is logged into your account right now. Do NOT open Pokémon GO until this order is
            marked Completed.
          </div>
        )}

        <div className="mt-10 border border-[#1f1f1f] bg-[#0a0a0a]">
          <div className="border-b border-[#1f1f1f] px-5 py-3 text-[10px] uppercase tracking-[0.25em] text-zinc-500">
            Items
          </div>
          <div className="divide-y divide-zinc-900">
            {order.items.map((i) => (
              <div key={i.product_id} className="flex justify-between px-5 py-4 text-xs">
                <span className="text-zinc-300">{i.name}{i.variant_label ? ` — ${i.variant_label}` : ""} <span className="text-zinc-600">× {i.quantity}</span></span>
                <span>{money(i.price * i.quantity)}</span>
              </div>
            ))}
          </div>
          <div className="flex justify-between border-t border-[#1f1f1f] px-5 py-4 text-xs uppercase tracking-[0.2em]">
            <span className="text-zinc-500">Total</span>
            <span data-testid="order-total" className="font-display text-base text-[#00ffcc]">{money(order.total)}</span>
          </div>
          {order.discount > 0 && (
            <p data-testid="order-discount" className="px-5 pb-4 text-[10px] uppercase tracking-[0.2em] text-[#00ffcc]">
              Coupon {order.coupon_code} · -{money(order.discount)} off {money(order.subtotal)}
            </p>
          )}
        </div>

        <p className="mt-6 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
          PTC credentials: encrypted · {order.ptc_username_masked}
        </p>
      </div>

      <div className="lg:col-span-5">
        <OrderChat orderId={order.id} />
      </div>
    </div>
  );
}
