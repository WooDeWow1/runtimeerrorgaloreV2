import { useCallback, useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { toast } from "sonner";

import { api, apiError, money } from "@/lib/api";

const Stat = ({ label, value }) => (
  <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-5">
    <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">{label}</p>
    <p className="mt-3 font-display text-2xl text-white">{value}</p>
  </div>
);

const MEDALS = ["text-[#f4d03f]", "text-zinc-300", "text-[#cd7f32]"];

export const AffiliatesTab = () => {
  const [data, setData] = useState(null);

  const load = useCallback(
    () =>
      api
        .get("/admin/affiliates")
        .then(({ data: d }) => setData(d))
        .catch((e) => toast.error(apiError(e))),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  const changeTier = async (row, tierId) => {
    try {
      await api.put(`/admin/affiliates/${row.customer_id}/tier`, null, { params: { tier_id: tierId } });
      toast.success(`${row.code} moved to a new rate`);
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  if (!data) return <p className="py-16 text-xs text-zinc-600">Loading promoters…</p>;

  return (
    <div data-testid="affiliates-tab" className="mt-10">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Promoters" value={data.stats.total_affiliates} />
        <Stat label="Commission paid" value={money(data.stats.commissions_all_time)} />
        <Stat label="Referred revenue" value={money(data.stats.attributed_revenue_all_time)} />
        <Stat label="Referred orders" value={data.stats.attributed_orders} />
      </div>

      {data.stats.pending_payout_requests > 0 && (
        <p
          data-testid="pending-payouts-note"
          className="mt-6 border border-[#f4d03f]/40 px-4 py-3 text-[10px] uppercase tracking-[0.2em] text-[#f4d03f]"
        >
          {data.stats.pending_payout_requests} payout request(s) waiting in SellAuth
        </p>
      )}

      <h3 className="mt-10 mb-4 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-zinc-500">
        <Trophy className="h-3 w-3" /> Leaderboard · {data.stats.window_days} day attribution
      </h3>

      {data.affiliates.length === 0 ? (
        <p data-testid="no-affiliates" className="text-xs text-zinc-600">
          No promoters yet.
        </p>
      ) : (
        <div className="space-y-3">
          {data.affiliates.map((a, n) => (
            <div
              key={a.customer_id}
              data-testid={`affiliate-row-${a.customer_id}`}
              className="flex flex-wrap items-center gap-x-6 gap-y-3 border border-[#1f1f1f] bg-[#0a0a0a] p-5"
            >
              <span className={`font-display text-xl ${MEDALS[n] || "text-zinc-700"}`}>
                #{n + 1}
              </span>
              <div className="min-w-[200px] flex-1">
                <p className="font-mono text-xs text-[#00ffcc]">{a.code}</p>
                <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                  {a.email}
                </p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">earned</p>
                <p className="font-display text-lg text-white">{money(a.earnings)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">unpaid</p>
                <p className="font-display text-lg text-[#f4d03f]">{money(a.balance)}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">referrals</p>
                <p className="font-display text-lg text-white">{a.referrals}</p>
              </div>
              <select
                data-testid={`affiliate-tier-${a.customer_id}`}
                value={a.tier_id || ""}
                onChange={(e) => changeTier(a, e.target.value)}
                className="bg-[#050505] px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
              >
                {data.tiers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {t.percentage}%
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
