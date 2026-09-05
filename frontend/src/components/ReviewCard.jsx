import { Star } from "lucide-react";
import { Pin, ShieldCheck } from "lucide-react";

export const Stars = ({ rating, size = "h-3.5 w-3.5" }) => (
  <div className="flex gap-0.5">
    {[1, 2, 3, 4, 5].map((n) => (
      <Star
        key={n}
        className={`${size} ${n <= rating ? "text-[#f4d03f]" : "text-zinc-700"}`}
        fill={n <= rating ? "currentColor" : "none"}
      />
    ))}
  </div>
);

export const ReviewCard = ({ review }) => (
  <article
    data-testid={`review-card-${review.id}`}
    className={`flex h-full flex-col border bg-[#0a0a0a] p-5 ${
      review.pinned ? "border-[#00ffcc]/40" : "border-[#1f1f1f]"
    }`}
  >
    <div className="flex items-center justify-between gap-3">
      <Stars rating={review.rating} />
      {review.pinned && (
        <span
          data-testid={`review-card-pinned-${review.id}`}
          className="flex items-center gap-1.5 text-[9px] uppercase tracking-[0.2em] text-[#00ffcc]"
        >
          <Pin className="h-3 w-3" /> Featured
        </span>
      )}
    </div>
    {review.title && (
      <h3 className="mt-3 font-display text-sm leading-tight tracking-tight">{review.title}</h3>
    )}
    <p className="mt-2 flex-1 whitespace-pre-line text-xs leading-relaxed text-zinc-400">
      {review.body}
    </p>
    <div className="mt-4 flex items-center gap-3 border-t border-zinc-900 pt-4">
      <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-300">
        {review.first_name}
      </span>
      <span className="flex items-center gap-1.5 border border-[#00ffcc]/40 px-2 py-1 text-[9px] uppercase tracking-[0.15em] text-[#00ffcc]">
        <ShieldCheck className="h-3 w-3" /> Verified Customer
      </span>
    </div>
  </article>
);
