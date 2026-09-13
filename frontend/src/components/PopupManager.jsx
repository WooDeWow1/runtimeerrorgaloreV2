import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check, Copy, X } from "lucide-react";

import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { COUPON_KEY, useCart } from "@/context/CartContext";

const SEEN_KEY = (id) => `pokeforge_popup_${id}`;
const VIEWS_KEY = "pokeforge_page_views";

const suppressed = (popup) => {
  const until = Number(localStorage.getItem(SEEN_KEY(popup.id)) || 0);
  return until > Date.now();
};

const suppress = (popup) =>
  localStorage.setItem(SEEN_KEY(popup.id), String(Date.now() + popup.suppress_days * 86400000));

export const PopupManager = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { items, coupon, applyCoupon } = useCart();
  const [popups, setPopups] = useState([]);
  const [active, setActive] = useState(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [offer, setOffer] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .get("/popups")
      .then(({ data }) => setPopups(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user]);

  const close = useCallback(() => {
    if (active) suppress(active);
    setActive(null);
    setOffer(null);
  }, [active]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  // Page view counter for page_views triggers.
  useEffect(() => {
    const views = Number(sessionStorage.getItem(VIEWS_KEY) || 0) + 1;
    sessionStorage.setItem(VIEWS_KEY, String(views));
  }, [location.pathname]);

  const eligible = useCallback(
    (popup) => {
      if (suppressed(popup)) return false;
      if (popup.paths?.length && !popup.paths.includes(location.pathname)) return false;
      return true;
    },
    [location.pathname]
  );

  // Delay / page-view triggers.
  useEffect(() => {
    if (active) return;
    const timers = [];
    popups
      .filter((p) => p.trigger !== "exit_checkout" && eligible(p))
      .forEach((p) => {
        if (p.trigger === "page_views") {
          const views = Number(sessionStorage.getItem(VIEWS_KEY) || 0);
          if (views >= p.page_views) setActive(p);
          return;
        }
        timers.push(setTimeout(() => setActive((cur) => cur || p), p.delay_seconds * 1000));
      });
    return () => timers.forEach(clearTimeout);
  }, [popups, eligible, active]);

  // Abandoned checkout: they were on /checkout with items and left without paying.
  const left = location.pathname !== "/checkout" && !location.pathname.startsWith("/payment");
  useEffect(() => {
    if (active) return;
    const wasOnCheckout = sessionStorage.getItem("pokeforge_on_checkout") === "1";
    if (location.pathname === "/checkout") {
      sessionStorage.setItem("pokeforge_on_checkout", "1");
      return;
    }
    if (location.pathname.startsWith("/payment")) {
      sessionStorage.removeItem("pokeforge_on_checkout");
      return;
    }
    // localStorage is checked as well: after a hard reload the coupon is re-priced async.
    if (!wasOnCheckout || !left || items.length === 0 || coupon) return;
    if (localStorage.getItem(COUPON_KEY)) return;
    const popup = popups.find((p) => p.trigger === "exit_checkout" && eligible(p));
    if (!popup) return;
    sessionStorage.removeItem("pokeforge_on_checkout");
    api
      .post(`/popups/${popup.id}/offer`)
      .then(({ data }) => {
        setOffer(data);
        setActive(popup);
      })
      .catch(() => {});
  }, [location.pathname, popups, items.length, coupon, eligible, active, left]);

  const join = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/popups/${active.id}/submit`, { email, name });
      toast.success(data.message);
      suppress(active);
      setActive(null);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(offer.code);
    setCopied(true);
    toast.success("Code copied");
  };

  const applyAndReturn = async () => {
    setBusy(true);
    const ok = await applyCoupon(offer.code);
    setBusy(false);
    suppress(active);
    setActive(null);
    navigate(ok ? "/checkout" : `/checkout?code=${offer.code}`);
  };

  if (!active) return null;

  const field =
    "w-full bg-[#050505] px-3 py-3 font-mono text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";

  return (
    <div
      data-testid="site-popup"
      className="fixed bottom-4 left-4 right-4 z-[60] mx-auto max-w-sm animate-in border border-[#00ffcc]/40 bg-[#0a0a0a] p-6 shadow-[0_0_50px_-10px_rgba(0,255,204,0.45)] sm:left-auto sm:right-6 sm:bottom-6"
    >
      <button
        data-testid="popup-close-btn"
        onClick={close}
        aria-label="Close"
        className="absolute right-3 top-3 text-zinc-600 transition-colors hover:text-white"
      >
        <X className="h-4 w-4" />
      </button>

      <p className="font-display text-lg leading-tight tracking-tight text-white">{active.title}</p>
      {active.body && (
        <p data-testid="popup-body" className="mt-3 text-xs leading-relaxed text-zinc-400">
          {active.body}
        </p>
      )}

      {active.type === "discount_offer" && offer && (
        <div className="mt-5">
          <div className="flex items-center justify-between gap-3 border border-[#00ffcc]/40 bg-[#00ffcc]/[0.06] px-4 py-3">
            <span data-testid="popup-coupon-code" className="font-display text-xl text-[#00ffcc]">
              {offer.code}
            </span>
            <button
              data-testid="popup-copy-code-btn"
              onClick={copy}
              className="text-zinc-400 transition-colors hover:text-[#00ffcc]"
              aria-label="Copy code"
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <p className="mt-2 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
            {offer.percent_off}% off · Event Passes excluded
          </p>
          <button
            data-testid="popup-apply-code-btn"
            disabled={busy}
            onClick={applyAndReturn}
            className="mt-4 w-full border border-[#00ffcc] py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
          >
            {busy ? "Applying…" : active.button_label}
          </button>
        </div>
      )}

      {active.type === "email_capture" && (
        <form onSubmit={join} className="mt-5 space-y-3">
          {active.collect_name && (
            <input
              data-testid="popup-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="First name"
              className={field}
            />
          )}
          <input
            data-testid="popup-email-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            className={field}
            required
          />
          <button
            data-testid="popup-submit-btn"
            disabled={busy}
            className="w-full border border-[#00ffcc] py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
          >
            {busy ? "Adding…" : active.button_label}
          </button>
        </form>
      )}

      <button
        data-testid="popup-dismiss-btn"
        onClick={close}
        className="mt-3 w-full text-[10px] uppercase tracking-[0.25em] text-zinc-600 transition-colors hover:text-zinc-300"
      >
        {active.dismiss_label}
      </button>
    </div>
  );
};
