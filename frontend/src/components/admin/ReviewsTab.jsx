import { useEffect, useState } from "react";
import { Check, Pin, PinOff, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";
import { Stars } from "@/components/ReviewCard";

export const ReviewsTab = () => {
  const [reviews, setReviews] = useState([]);
  const [filter, setFilter] = useState("pending");

  const load = () =>
    api
      .get("/admin/reviews", { params: filter === "all" ? {} : { status: filter } })
      .then(({ data }) => setReviews(data))
      .catch(() => {});

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const approve = async (r) => {
    try {
      const { data } = await api.post(`/admin/reviews/${r.id}/approve`);
      toast.success(
        data.coupon ? `Review published · coupon ${data.coupon.code} issued` : "Review published"
      );
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const decline = async (r) => {
    if (!window.confirm("Decline this review? It is deleted and the order is locked from reviewing again.")) return;
    try {
      await api.delete(`/admin/reviews/${r.id}`);
      toast.success("Review declined");
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const remove = async (r) => {
    if (!window.confirm("Delete this review? The order stays eligible for a new review.")) return;
    try {
      await api.delete(`/admin/reviews/${r.id}`, { params: { lock: false } });
      toast.success("Review deleted");
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const togglePin = async (r) => {
    try {
      await api.post(`/admin/reviews/${r.id}/pin`, null, { params: { pinned: !r.pinned } });
      toast.success(r.pinned ? "Unpinned" : "Pinned to top");
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  return (
    <div className="mt-10" data-testid="reviews-panel">
      <h2 className="font-display text-sm uppercase tracking-[0.2em]">Customer reviews</h2>
      <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
        Approving publishes the review and generates the customer's single-use reward coupon (any
        star rating). Pinned reviews always lead the homepage and reviews page. Decline deletes the
        review and locks that order; Delete just clears the row and leaves the order eligible.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        {["pending", "approved", "all"].map((f) => (
          <button
            key={f}
            data-testid={`review-filter-${f}`}
            onClick={() => setFilter(f)}
            className={`border px-4 py-2 text-[10px] uppercase tracking-[0.25em] transition-colors ${
              filter === f ? "border-[#00ffcc] text-[#00ffcc]" : "border-zinc-800 text-zinc-500 hover:text-white"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="mt-8 space-y-4" data-testid="admin-reviews-list">
        {reviews.length === 0 && (
          <p data-testid="reviews-empty" className="text-xs text-zinc-600">
            Nothing here right now.
          </p>
        )}
        {reviews.map((r) => (
          <div
            key={r.id}
            data-testid={`admin-review-${r.id}`}
            className="border border-[#1f1f1f] bg-[#0a0a0a] p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-[240px] flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <Stars rating={r.rating} />
                  <span
                    className={`border px-2 py-1 text-[9px] uppercase tracking-[0.2em] ${
                      r.status === "approved"
                        ? "border-[#00ffcc]/50 text-[#00ffcc]"
                        : "border-[#f4d03f]/50 text-[#f4d03f]"
                    }`}
                  >
                    {r.status}
                  </span>
                  {r.pinned && (
                    <span
                      data-testid={`review-pinned-badge-${r.id}`}
                      className="flex items-center gap-1.5 border border-[#9966cc]/60 px-2 py-1 text-[9px] uppercase tracking-[0.2em] text-[#9966cc]"
                    >
                      <Pin className="h-3 w-3" /> pinned
                    </span>
                  )}
                </div>
                <p className="mt-3 text-xs font-bold">{r.title}</p>
                <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-zinc-400">{r.body}</p>
                <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                  shown as {r.anonymous || !r.display_name ? "Valued Customer" : r.display_name} ·{" "}
                  {r.user_email} · order #{r.order_id.slice(-8)}
                  {r.coupon_code ? ` · coupon ${r.coupon_code}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {r.status !== "approved" && (
                  <button
                    data-testid={`approve-review-${r.id}`}
                    onClick={() => approve(r)}
                    className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
                  >
                    <Check className="h-3 w-3" /> Approve
                  </button>
                )}
                <button
                  data-testid={`pin-review-${r.id}`}
                  onClick={() => togglePin(r)}
                  className={`flex items-center gap-2 border px-4 py-2 text-[10px] uppercase tracking-[0.2em] transition-colors ${
                    r.pinned
                      ? "border-[#9966cc] text-[#9966cc] hover:bg-[#9966cc] hover:text-black"
                      : "border-zinc-800 text-zinc-400 hover:border-[#9966cc] hover:text-[#9966cc]"
                  }`}
                >
                  {r.pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
                  {r.pinned ? "Unpin" : "Pin to top"}
                </button>
                <button
                  data-testid={`decline-review-${r.id}`}
                  onClick={() => decline(r)}
                  className="flex items-center gap-2 border border-zinc-800 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#ff9500] hover:text-[#ff9500]"
                >
                  <X className="h-3 w-3" /> Decline
                </button>
                <button
                  data-testid={`delete-review-${r.id}`}
                  onClick={() => remove(r)}
                  className="flex items-center gap-2 border border-zinc-800 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#ff3b30] hover:text-[#ff3b30]"
                >
                  <Trash2 className="h-3 w-3" /> Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
