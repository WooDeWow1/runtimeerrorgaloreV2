import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Wallet } from "lucide-react";
import { toast } from "sonner";

import { api, apiError, money } from "@/lib/api";

export const PayoutsTab = () => {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(
    () => api.get("/admin/payouts").then(({ data }) => setRows(data)).catch((e) => {
      toast.error(apiError(e));
      setRows([]);
    }),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  const markPaid = async (row) => {
    if (!window.confirm(`Mark ${money(row.amount)} to ${row.name} as paid?`)) return;
    setBusy(row.id);
    try {
      await api.post(`/admin/payouts/${row.id}/paid`);
      toast.success("Payout cleared in SellAuth");
      load();
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(null);
    }
  };

  if (!rows) return <p className="py-16 text-xs text-zinc-600">Loading payout requests…</p>;

  const total = rows.reduce((sum, r) => sum + r.amount, 0);

  return (
    <div data-testid="payouts-tab" className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[10px] leading-relaxed text-zinc-600">
          Pending affiliate payout requests from SellAuth. Pay the person by hand, then clear the
          request here.
        </p>
        <p className="font-display text-xl text-[#f4d03f]" data-testid="payouts-total">
          {money(total)} owed
        </p>
      </div>

      {rows.length === 0 ? (
        <p data-testid="no-payouts" className="mt-8 text-xs text-zinc-600">
          No payout requests waiting. Nothing to do.
        </p>
      ) : (
        <div className="mt-8 space-y-3">
          {rows.map((r) => (
            <div
              key={r.id}
              data-testid={`payout-row-${r.id}`}
              className="flex flex-wrap items-center gap-x-6 gap-y-3 border border-[#1f1f1f] bg-[#0a0a0a] p-5"
            >
              <Wallet className="h-4 w-4 text-[#f4d03f]" />
              <div className="min-w-[200px] flex-1">
                <p className="text-xs text-white">{r.name}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                  code {r.code} · requested {r.requested_at ? r.requested_at.slice(0, 10) : "—"}
                </p>
              </div>
              <div className="min-w-[180px]">
                <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">pay to</p>
                <p className="mt-1 break-all font-mono text-[11px] text-zinc-300">{r.details}</p>
              </div>
              <div>
                <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">amount</p>
                <p className="font-display text-lg text-[#00ffcc]">{money(r.amount)}</p>
              </div>
              <button
                data-testid={`mark-paid-${r.id}`}
                disabled={busy === r.id}
                onClick={() => markPaid(r)}
                className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
              >
                <BadgeCheck className="h-3 w-3" /> {busy === r.id ? "Clearing…" : "Mark as paid"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
