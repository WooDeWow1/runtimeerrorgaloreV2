import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { ReviewCard, Stars } from "@/components/ReviewCard";

const PER_PAGE = 3;
const ROTATE_MS = 7000;

export const ReviewCarousel = () => {
  const [data, setData] = useState({ reviews: [], count: 0, average: null });
  const [page, setPage] = useState(0);

  useEffect(() => {
    api.get("/reviews", { params: { limit: 24 } }).then(({ data }) => setData(data)).catch(() => {});
  }, []);

  const pages = Math.max(1, Math.ceil(data.reviews.length / PER_PAGE));

  useEffect(() => {
    if (pages < 2) return;
    const timer = setInterval(() => setPage((p) => (p + 1) % pages), ROTATE_MS);
    return () => clearInterval(timer);
  }, [pages]);

  if (data.reviews.length === 0) return null;

  const visible = data.reviews.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE);

  return (
    <div data-testid="home-review-carousel" className="mt-16 flex flex-col items-end">
      <div className="flex w-full flex-wrap items-center justify-end gap-4">
        <div className="mr-auto lg:mr-0">
          <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// verified buyers</p>
          <div className="mt-2 flex items-center gap-3">
            <Stars rating={Math.round(data.average)} />
            <span className="text-xs text-zinc-400">
              <span className="text-[#00ffcc]">{data.average}</span> from {data.count} review
              {data.count === 1 ? "" : "s"}
            </span>
          </div>
        </div>
        {pages > 1 && (
          <div className="flex gap-2">
            <button
              data-testid="carousel-prev"
              aria-label="Previous reviews"
              onClick={() => setPage((p) => (p - 1 + pages) % pages)}
              className="border border-zinc-800 p-2 text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              data-testid="carousel-next"
              aria-label="Next reviews"
              onClick={() => setPage((p) => (p + 1) % pages)}
              className="border border-zinc-800 p-2 text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        <Link
          to="/reviews"
          data-testid="carousel-all-reviews-link"
          className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 transition-colors hover:text-[#00ffcc]"
        >
          Read all reviews →
        </Link>
      </div>

      <div className="mt-6 grid w-full gap-6 sm:grid-cols-2 lg:w-[70%] lg:grid-cols-3">
        {visible.map((r) => (
          <ReviewCard key={r.id} review={r} />
        ))}
      </div>
    </div>
  );
};
