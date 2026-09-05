import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Star } from "lucide-react";
import { api, money } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";
import { ReviewDialog } from "@/components/ReviewDialog";
import { useAuth } from "@/context/AuthContext";

const ACTIVE = ["pending", "processing", "awaiting_payment"];

const pill = "border px-4 py-2 text-[10px] uppercase tracking-[0.2em]";

// Where this order sits in the review → approval → reward flow.
const ReviewSlot = ({ orderId, info, onLeaveReview }) => {
  if (!info) {
    return (
      <button
        data-testid={`leave-review-${orderId}`}
        onClick={onLeaveReview}
        className={`flex items-center gap-2 border-[#f4d03f] text-[#f4d03f] transition-colors hover:bg-[#f4d03f] hover:text-black ${pill}`}
      >
        <Star className="h-3 w-3" /> Leave a review
      </button>
    );
  }
  if (info.status === "declined") return null;
  if (info.status === "pending") {
    return (
      <span
        data-testid={`review-submitted-${orderId}`}
        className={`border-[#f4d03f]/40 text-[#f4d03f] ${pill}`}
      >
        Review submitted — pending
      </span>
    );
  }
  const coupon = info.coupon || { state: "unavailable" };
  if (coupon.state === "unavailable") {
    return (
      <span
        data-testid={`review-coupon-unavailable-${orderId}`}
        className={`border-zinc-800 text-zinc-500 ${pill}`}
      >
        Coupon no longer available
      </span>
    );
  }
  if (coupon.state === "expired") {
    return (
      <span
        data-testid={`review-coupon-expired-${orderId}`}
        className={`border-zinc-800 text-zinc-500 ${pill}`}
      >
        <span className="font-mono">{coupon.code}</span> · Expired
      </span>
    );
  }
  return (
    <span
      data-testid={`review-coupon-${orderId}`}
      className={`border-[#00ffcc]/40 text-[#00ffcc] ${pill}`}
    >
      {coupon.state === "redeemed" ? (
        <>
          <span className="font-mono">{coupon.code}</span> · Redeemed
        </>
      ) : (
        <>
          Coupon credited ·{" "}
          <span className="font-mono">{coupon.code}</span>
          {coupon.percent_off ? ` · ${coupon.percent_off}% off` : ""}
        </>
      )}
    </span>
  );
};

export default function MyOrders() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [openChat, setOpenChat] = useState(null);
  const [reviewed, setReviewed] = useState({});
  const [reviewOrder, setReviewOrder] = useState(null);

  // Which completed orders already carry a review, so the button becomes a confirmation.
  const loadReviewStatus = useCallback((list) => {
    const ids = list.filter((o) => o.status === "completed").map((o) => o.id);
    if (ids.length === 0) return;
    api
      .get("/reviews/status", { params: { order_ids: ids.join(",") } })
      .then(({ data }) => setReviewed(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (user) {
      api
        .get("/orders")
        .then(({ data }) => {
          setOrders(data);
          loadReviewStatus(data);
        })
        .catch(() => {});
      return;
    }
    const ids = JSON.parse(localStorage.getItem("pokeforge_guest_orders") || "[]").slice(0, 20);
    Promise.all(
      ids.map((id) => api.get(`/orders/${id}`).then(({ data }) => data).catch(() => null))
    ).then((list) => {
      const found = list.filter(Boolean);
      setOrders(found);
      loadReviewStatus(found);
      // Drop ids we can no longer read (claimed on another account, or deleted).
      localStorage.setItem("pokeforge_guest_orders", JSON.stringify(found.map((o) => o.id)));
    });
  }, [user, loadReviewStatus]);

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
          {o.status === "completed" && (
            <ReviewSlot
              orderId={o.id}
              info={reviewed[o.id]}
              onLeaveReview={() => setReviewOrder(o.id)}
            />
          )}
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
      {reviewOrder && (
        <ReviewDialog
          orderId={reviewOrder}
          open={!!reviewOrder}
          onOpenChange={(next) => !next && setReviewOrder(null)}
          onSubmitted={() =>
            setReviewed((prev) => ({ ...prev, [reviewOrder]: { status: "pending" } }))
          }
        />
      )}
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
