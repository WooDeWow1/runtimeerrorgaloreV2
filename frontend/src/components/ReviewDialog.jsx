import { useState } from "react";
import { Star } from "lucide-react";
import { Turnstile } from "@marsidev/react-turnstile";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const SITE_KEY = process.env.REACT_APP_TURNSTILE_SITE_KEY;
const MIN = 150;
const MAX = 650;

export const ReviewDialog = ({ orderId, open, onOpenChange, onSubmitted }) => {
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [token, setToken] = useState(null);
  const [captchaBroken, setCaptchaBroken] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // { coupon }

  const submit = async (e) => {
    e.preventDefault();
    if (body.trim().length < MIN) return toast.error(`Please write at least ${MIN} characters`);
    if (!token && !captchaBroken) return toast.error("Please complete the verification first");
    setBusy(true);
    try {
      const { data } = await api.post("/reviews", {
        order_id: orderId,
        rating,
        title: title.trim(),
        body: body.trim(),
        turnstile_token: token || "captcha-unavailable",
      });
      setDone(data);
      onSubmitted();
    } catch (err) {
      toast.error(apiError(err));
      setToken(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="review-dialog"
        className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-lg overflow-y-auto border border-[#1f1f1f] bg-[#0a0a0a] text-white"
      >
        {done ? (
          <div data-testid="review-thanks" className="py-4 text-center">
            <p className="font-display text-2xl tracking-tight text-[#00ffcc]">
              Thank you for your feedback
            </p>
            <p className="mt-3 text-xs leading-relaxed text-zinc-400">
              Your review is with our team and goes live once approved.
            </p>
            <div
              data-testid="review-coupon-pending"
              className="mt-6 border border-[#00ffcc]/40 bg-[#00ffcc]/[0.06] p-5"
            >
              <p className="text-[10px] uppercase tracking-[0.25em] text-[#00ffcc]">
                Reward on approval
              </p>
              <p className="mt-3 text-xs leading-relaxed text-zinc-400">
                Once a team member approves your review, a single-use discount code is credited to
                your account. It appears right here on this orders page, and we email it to you too.
              </p>
            </div>
            <button
              data-testid="close-review-thanks"
              onClick={() => onOpenChange(false)}
              className="mt-6 border border-zinc-700 px-6 py-2.5 text-[10px] uppercase tracking-[0.25em] text-zinc-300 hover:border-[#00ffcc] hover:text-[#00ffcc]"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <DialogHeader className="text-left">
              <DialogTitle className="font-display text-xl tracking-tight">Leave a review</DialogTitle>
              <DialogDescription className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                Order #{orderId.slice(-8)}
              </DialogDescription>
            </DialogHeader>

            <div className="mt-5 flex gap-2" data-testid="review-stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  data-testid={`review-star-${n}`}
                  onClick={() => setRating(n)}
                  className="transition-transform hover:scale-110"
                >
                  <Star
                    className={`h-7 w-7 ${n <= rating ? "text-[#f4d03f]" : "text-zinc-700"}`}
                    fill={n <= rating ? "currentColor" : "none"}
                  />
                </button>
              ))}
            </div>

            <label className="mt-6 mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500">
              Title
            </label>
            <input
              data-testid="review-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={80}
              required
              className="w-full bg-[#050505] px-3 py-2.5 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
            />

            <label className="mt-5 mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500">
              Your review
            </label>
            <textarea
              data-testid="review-body-input"
              value={body}
              onChange={(e) => setBody(e.target.value.slice(0, MAX))}
              className="h-40 w-full bg-[#050505] px-3 py-2.5 text-xs leading-relaxed text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
              placeholder="How was the delivery, the speed and the support?"
              required
            />
            <p
              data-testid="review-char-count"
              className={`mt-2 text-[10px] uppercase tracking-[0.2em] ${
                body.trim().length < MIN ? "text-zinc-600" : "text-[#00ffcc]"
              }`}
            >
              {body.trim().length} / {MIN} minimum · {MAX} max
            </p>

            <div className="mt-5" data-testid="review-turnstile">
              {SITE_KEY ? (
                <Turnstile
                  siteKey={SITE_KEY}
                  onSuccess={(t) => {
                    setToken(t);
                    setCaptchaBroken(false);
                  }}
                  onError={() => {
                    // The preview sandbox is not a registered Turnstile hostname.
                    setToken(null);
                    setCaptchaBroken(true);
                  }}
                  onExpire={() => setToken(null)}
                  options={{ theme: "dark", size: "flexible", action: "review" }}
                />
              ) : (
                <p className="text-[10px] text-[#ff3b30]">CAPTCHA is not configured.</p>
              )}
              {captchaBroken && (
                <p data-testid="captcha-unavailable" className="mt-2 text-[10px] leading-relaxed text-zinc-500">
                  Verification could not load on this domain — your review is still checked on the server.
                </p>
              )}
            </div>

            <div className="mt-6 flex gap-3">
              <button
                data-testid="submit-review-btn"
                disabled={busy || body.trim().length < MIN}
                className="border border-[#00ffcc] px-6 py-2.5 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent"
              >
                {busy ? "Sending…" : "Submit review"}
              </button>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="border border-zinc-800 px-6 py-2.5 text-[10px] uppercase tracking-[0.25em] text-zinc-400 hover:text-white"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};
