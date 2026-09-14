import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Loader2, Pencil, Share2, Wallet } from "lucide-react";
import { toast } from "sonner";

import { api, apiError, money } from "@/lib/api";
import { PayoutDialog } from "@/components/PayoutDialog";
import { EditCodeDialog } from "@/components/EditCodeDialog";
import { ShareButtons } from "@/components/ShareButtons";

const Stat = ({ label, value, accent }) => (
  <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-5">
    <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">{label}</p>
    <p className={`mt-3 font-display text-2xl ${accent || "text-white"}`}>{value}</p>
  </div>
);

export const ReferEarn = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [payoutOpen, setPayoutOpen] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get("/affiliate/me");
      setData(d);
    } catch (e) {
      toast.error(apiError(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const enroll = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.post("/affiliate/enroll");
      setData(d);
      toast.success("You're in — your referral link is ready");
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.link);
      setCopied(true);
      toast.success("Referral link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Some browsers block clipboard writes: show the link so it can be copied by hand.
      toast.error("Copy blocked by your browser — select the link and copy it manually");
    }
  };

  if (!data) {
    return (
      <div data-testid="refer-loading" className="flex items-center gap-3 py-16 text-xs text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading your promoter panel…
      </div>
    );
  }

  if (!data.program_enabled) {
    return (
      <p data-testid="refer-disabled" className="py-16 text-xs text-zinc-500">
        The promoter program is closed right now. Check back soon.
      </p>
    );
  }

  const c = data.commission || {};

  return (
    <div data-testid="refer-earn-panel" className="py-2">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h2 className="font-display text-2xl text-white">Refer &amp; earn</h2>
          <p className="mt-2 max-w-xl text-xs leading-relaxed text-zinc-500">
            Share your link and earn{" "}
            <span className="text-[#00ffcc]">
              {c.min_percent}% – {c.max_percent}%
            </span>{" "}
            commission on every order your referrals place. No minimum order. No cap
            on what you can earn.
            {c.excluded_products?.length ? " Event Passes earn 0%." : ""}
          </p>
        </div>
        {data.is_affiliate && data.payout?.enabled && (
          <button
            data-testid="request-payout-btn"
            onClick={() => setPayoutOpen(true)}
            className="flex items-center gap-2 border border-[#00ffcc] px-5 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
          >
            <Wallet className="h-3 w-3" /> Request payout
          </button>
        )}
      </div>

      {!data.is_affiliate ? (
        <div className="mt-8 border border-[#00ffcc]/30 bg-[#00ffcc]/[0.04] p-8">
          <p className="text-xs leading-relaxed text-zinc-400">
            You are not a promoter yet. One tap creates your unique link — no application, no wait.
          </p>
          <button
            data-testid="become-promoter-btn"
            disabled={busy}
            onClick={enroll}
            className="mt-6 flex items-center gap-2 border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600"
          >
            <Share2 className="h-3 w-3" /> {busy ? "Setting you up…" : "Become a promoter"}
          </button>
        </div>
      ) : (
        <>
          <div className="mt-8 border border-[#00ffcc]/30 bg-[#00ffcc]/[0.04] p-6">
            <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">
              Your referral link
            </p>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
              <code
                data-testid="referral-link"
                className="flex-1 overflow-x-auto whitespace-nowrap border border-[#1f1f1f] bg-[#050505] px-4 py-3 font-mono text-xs text-[#00ffcc]"
              >
                {data.link}
              </code>
              <button
                data-testid="copy-referral-btn"
                onClick={copy}
                className="flex items-center justify-center gap-2 border border-[#00ffcc] px-5 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
              >
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
              code {data.code}
              {data.code_editable && !data.code_change_used && (
                <button
                  data-testid="edit-code-btn"
                  onClick={() => setCodeOpen(true)}
                  className="flex items-center gap-1.5 border border-zinc-800 px-3 py-1.5 tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
                >
                  <Pencil className="h-3 w-3" /> Edit my code
                </button>
              )}
              {data.code_change_used && (
                <span data-testid="code-locked-note" className="text-zinc-700">
                  · personalised
                </span>
              )}
            </p>
            <EditCodeDialog
              open={codeOpen}
              onOpenChange={setCodeOpen}
              current={data.code}
              onSaved={load}
            />
            <ShareButtons link={data.link} />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Available balance"
              value={money(data.balance)}
              accent="text-[#00ffcc]"
              data-testid="affiliate-balance"
            />
            <Stat label="Lifetime earnings" value={money(data.lifetime_earnings)} />
            <Stat label="Referrals" value={data.referrals_count} />
            <Stat
              label="Commission"
              value={`${c.min_percent}–${c.max_percent}%`}
              accent="text-[#f4d03f]"
            />
          </div>

          {data.payout?.open_request && (
            <p
              data-testid="open-payout-request"
              className="mt-6 border border-[#f4d03f]/40 px-4 py-3 text-[10px] uppercase tracking-[0.2em] text-[#f4d03f]"
            >
              Payout of {money(data.payout.open_request.amount)} pending review
            </p>
          )}

          <PayoutDialog
            open={payoutOpen}
            onOpenChange={setPayoutOpen}
            balance={data.balance}
            minimum={data.payout?.min_amount}
            methods={data.payout?.methods || {}}
            onDone={load}
          />
        </>
      )}
    </div>
  );
};
