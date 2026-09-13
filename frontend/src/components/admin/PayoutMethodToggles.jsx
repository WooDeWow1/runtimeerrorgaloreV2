import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Switch } from "@/components/ui/switch";
import { api, apiError } from "@/lib/api";

export const PayoutMethodToggles = () => {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/admin/settings/payout-methods")
      .then(({ data }) => setRows(data))
      .catch((e) => {
        toast.error(apiError(e));
        setRows([]);
      });
  }, []);

  const toggle = async (key, enabled) => {
    const next = rows.map((r) => (r.key === key ? { ...r, enabled } : r));
    setBusy(true);
    try {
      const { data } = await api.put("/admin/settings/payout-methods", {
        methods: Object.fromEntries(next.map((r) => [r.key, r.enabled])),
      });
      setRows(data);
      toast.success("Payout methods updated");
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(false);
    }
  };

  if (!rows) return null;

  return (
    <div
      data-testid="payout-methods-panel"
      className="border border-[#1f1f1f] bg-[#0a0a0a] p-5"
    >
      <p className="text-[10px] uppercase tracking-[0.25em] text-[#00ffcc]">Payout methods</p>
      <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
        Only the methods switched on here appear to customers when they request a payout.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => (
          <div
            key={r.key}
            data-testid={`payout-method-row-${r.key}`}
            className="flex items-center justify-between gap-4 border border-[#1f1f1f] bg-[#050505] px-4 py-3"
          >
            <span className="text-xs text-white">{r.name}</span>
            <Switch
              data-testid={`payout-method-toggle-${r.key}`}
              checked={r.enabled}
              disabled={busy}
              onCheckedChange={(v) => toggle(r.key, v)}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
