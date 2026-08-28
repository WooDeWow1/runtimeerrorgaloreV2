import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import { api, money } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";
import { useAuth } from "@/context/AuthContext";

const ACTIVE = ["pending", "processing", "awaiting_payment"];

export default function MyOrders() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [openChat, setOpenChat] = useState(null);

  useEffect(() => {
    if (user) {
      api.get("/orders").then(({ data }) => setOrders(data)).catch(() => {});
      return;
    }
    const ids = JSON.parse(localStorage.getItem("pokeforge_guest_orders") || "[]").slice(0, 20);
    Promise.all(
      ids.map((id) => api.get(`/orders/${id}`).then(({ data }) => data).catch(() => null))
    ).then((list) => {
      const found = list.filter(Boolean);
      setOrders(found);
      // Drop ids we can no longer read (claimed on another account, or deleted).
      localStorage.setItem("pokeforge_guest_orders", JSON.stringify(found.map((o) => o.id)));
    });
  }, [user]);

  const Row = ({ o }) => (
    <div data-testid={`order-row-${o.id}`} className="border border-[#1f1f1f] bg-[#0a0a0a]">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">#{o.id.slice(-8)}</p>
          <p className="mt-2 text-xs text-zinc-200">
            {o.items.map((i) => `${i.name}${i.variant_label ? ` — ${i.variant_label}` : ""} ×${i.quantity}`).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-display text-sm text-[#00ffcc]">{money(o.total)}</span>
          <StatusBadge status={o.status} testId={`order-status-${o.id}`} />
          <button
            data-testid={`open-chat-${o.id}`}
            onClick={() => setOpenChat((prev) => (prev === o.id ? null : o.id))}
            className="flex items-center gap-2 border border-zinc-700 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
          >
            <MessageSquare className="h-3 w-3" />
            {openChat === o.id ? "Close chat" : "Open chat"}
          </button>
          <Link
            to={`/orders/${o.id}`}
            data-testid={`order-details-${o.id}`}
            className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 hover:text-[#00ffcc]"
          >
            Details →
          </Link>
        </div>
      </div>
      {openChat === o.id && (
        <div className="border-t border-[#1f1f1f] p-5">
          <OrderChat orderId={o.id} />
        </div>
      )}
    </div>
  );

  const active = orders.filter((o) => ACTIVE.includes(o.status));
  const past = orders.filter((o) => ["completed", "cancelled"].includes(o.status));
  const other = orders.filter(
    (o) => !ACTIVE.includes(o.status) && !["completed", "cancelled"].includes(o.status)
  );

  return (
    <div data-testid="my-orders-page" className="mx-auto max-w-[1200px] px-5 py-16 lg:px-10 lg:py-24">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// trainer console</p>
      <h1 className="mt-4 font-display text-3xl tracking-tighter">
        {user ? user.name : "Guest orders"}
      </h1>
      {!user && (
        <p className="mt-4 max-w-lg text-xs leading-relaxed text-zinc-500">
          These orders are remembered on this device only.{" "}
          <Link to="/login" className="text-[#00ffcc] hover:underline">
            Sign in
          </Link>{" "}
          to see them anywhere.
        </p>
      )}

      <section className="mt-14">
        <h2 className="mb-6 text-[10px] uppercase tracking-[0.3em] text-zinc-500">Active orders</h2>
        <div className="space-y-4">
          {active.length === 0 && (
            <p data-testid="no-active-orders" className="text-xs text-zinc-600">No active orders.</p>
          )}
          {active.map((o) => <Row key={o.id} o={o} />)}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="mb-6 text-[10px] uppercase tracking-[0.3em] text-zinc-500">History</h2>
        <div className="space-y-4">
          {past.length === 0 && <p className="text-xs text-zinc-600">Nothing archived yet.</p>}
          {past.map((o) => <Row key={o.id} o={o} />)}
        </div>
      </section>

      {other.length > 0 && (
        <section className="mt-16" data-testid="other-orders-section">
          <h2 className="mb-6 text-[10px] uppercase tracking-[0.3em] text-zinc-500">Other</h2>
          <div className="space-y-4">
            {other.map((o) => <Row key={o.id} o={o} />)}
          </div>
        </section>
      )}
    </div>
  );
}
