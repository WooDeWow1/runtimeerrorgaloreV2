import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ReviewCard, Stars } from "@/components/ReviewCard";

export default function Reviews() {
  const [data, setData] = useState({ reviews: [], count: 0, average: null });

  useEffect(() => {
    api.get("/reviews").then(({ data }) => setData(data)).catch(() => {});
  }, []);

  return (
    <div data-testid="reviews-page" className="mx-auto max-w-[1400px] px-5 py-14 lg:px-10 lg:py-20">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// verified buyers</p>
      <h1 className="mt-4 font-display text-4xl tracking-tighter sm:text-5xl lg:text-6xl">Reviews</h1>

      {/* An average off one or two reviews reads weak, so it stays hidden until there are 3. */}
      {data.count >= 3 && (
        <div data-testid="reviews-average" className="mt-6 flex flex-wrap items-center gap-4">
          <Stars rating={Math.round(data.average)} size="h-5 w-5" />
          <p className="text-base text-zinc-300">
            <span className="font-display text-xl text-[#00ffcc]">{data.average}</span> from{" "}
            {data.count} review{data.count === 1 ? "" : "s"}
          </p>
        </div>
      )}
      {data.count === 0 && (
        <p className="mt-6 max-w-xl text-sm leading-relaxed text-zinc-500">
          No reviews published yet. Every review here comes from a completed, delivered order.
        </p>
      )}

      <div
        data-testid="reviews-explainer"
        className="mt-8 max-w-3xl border-l-2 border-[#00ffcc]/40 bg-[#0a0a0a]/60 px-5 py-4"
      >
        <p className="text-[10px] uppercase tracking-[0.25em] text-[#00ffcc]">
          How our reviews work
        </p>
        <p className="mt-3 text-xs leading-relaxed text-zinc-400">
          Real reviews from real customers. Only customers who have completed an order can leave a
          review, and every review is tied to that order. The rating above is the average across all
          reviews.
        </p>
        <p className="mt-3 text-xs leading-relaxed text-zinc-400">
          We give customers a one-time discount code for taking the time to leave feedback. The code
          is the same whether the review is good or bad, and we don't edit or filter what customers
          write.
        </p>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.reviews.map((r) => (
          <ReviewCard key={r.id} review={r} />
        ))}
      </div>
    </div>
  );
}
