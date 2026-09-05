import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";

const blank = {
  code: "",
  discount_type: "percent",
  percent_off: "",
  amount_off: "",
  one_per_customer: false,
  active: true,
  min_subtotal: "",
  max_uses: "",
  expires_at: "",
  excluded_categories: [],
  note: "",
};

const toForm = (c) =>
  !c
    ? blank
    : {
        code: c.code,
        discount_type: c.discount_type || "percent",
        percent_off: c.percent_off ?? "",
        amount_off: c.amount_off ?? "",
        one_per_customer: !!c.one_per_customer,
        active: c.active !== false,
        min_subtotal: c.min_subtotal ?? "",
        max_uses: c.max_uses ?? "",
        expires_at: c.expires_at ? c.expires_at.slice(0, 10) : "",
        excluded_categories: c.excluded_categories || [],
        note: c.note || "",
      };

// Support lookup: an auto code is either still live, spent, or timed out.
const autoStatus = (c) => {
  if (c.used_count > 0) {
    return {
      label: `redeemed${c.redeemed_at ? ` ${c.redeemed_at.slice(0, 10)}` : ""}`,
      tone: "text-[#00ffcc]",
    };
  }
  const expired = c.expires_at && new Date(c.expires_at) < new Date();
  if (expired || c.active === false) return { label: "expired", tone: "text-[#ff3b30]" };
  return { label: "unredeemed", tone: "text-[#f4d03f]" };
};

export const CouponsTab = ({ categories }) => {
  const [coupons, setCoupons] = useState([]);
  const [source, setSource] = useState("manual");
  const [reviewCfg, setReviewCfg] = useState(null);
  const [editing, setEditing] = useState(null); // null | "new" | coupon
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .get("/admin/coupons", { params: { source } })
      .then(({ data }) => setCoupons(data))
      .catch(() => {});
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  useEffect(() => {
    api.get("/admin/settings/reviews").then(({ data }) => setReviewCfg(data)).catch(() => {});
  }, []);

  const saveReviewCfg = async (next) => {
    setReviewCfg(next);
    try {
      const { data } = await api.put("/admin/settings/reviews", {
        enabled: next.enabled,
        percent_off: Number(next.percent_off),
        expiry_days: Number(next.expiry_days),
      });
      setReviewCfg(data);
      toast.success("Review coupon settings saved");
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const set = (k) => (e) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const open = (coupon) => {
    setEditing(coupon || "new");
    setForm(toForm(coupon));
  };

  const toggleExcluded = (key) =>
    setForm((f) => ({
      ...f,
      excluded_categories: f.excluded_categories.includes(key)
        ? f.excluded_categories.filter((k) => k !== key)
        : [...f.excluded_categories, key],
    }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const payload = {
      code: form.code.trim().toUpperCase(),
      discount_type: form.discount_type,
      percent_off: form.discount_type === "percent" ? Number(form.percent_off) : null,
      amount_off: form.discount_type === "fixed" ? Number(form.amount_off) : null,
      one_per_customer: form.one_per_customer,
      active: form.active,
      min_subtotal: form.min_subtotal === "" ? null : Number(form.min_subtotal),
      max_uses: form.max_uses === "" ? null : Number(form.max_uses),
      expires_at: form.expires_at ? new Date(`${form.expires_at}T23:59:59Z`).toISOString() : null,
      excluded_categories: form.excluded_categories,
      excluded_product_ids: [],
      note: form.note,
    };
    try {
      if (editing === "new") await api.post("/admin/coupons", payload);
      else await api.put(`/admin/coupons/${editing.id}`, payload);
      toast.success("Coupon saved");
      setEditing(null);
      load();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (c) => {
    if (!window.confirm(`Delete code ${c.code}? This cannot be undone.`)) return;
    try {
      await api.delete(`/admin/coupons/${c.id}`);
      toast.success(`${c.code} deleted`);
      load();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div className="mt-10" data-testid="coupons-panel">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-sm uppercase tracking-[0.2em]">Discount codes</h2>
          <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
            Codes are applied on this site and the final total is sent to SellAuth. Event Passes are
            always excluded — a code applies only to the eligible items in a mixed cart.
          </p>
        </div>
        <button
          data-testid="new-coupon-btn"
          onClick={() => open(null)}
          className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
        >
          <Plus className="h-3 w-3" /> New code
        </button>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        {[
          { key: "manual", label: "manual" },
          { key: "auto", label: "auto-generated" },
        ].map((t) => (
          <button
            key={t.key}
            data-testid={`coupon-source-${t.key}`}
            onClick={() => setSource(t.key)}
            className={`border px-4 py-2 text-[10px] uppercase tracking-[0.25em] transition-colors ${
              source === t.key ? "border-[#00ffcc] text-[#00ffcc]" : "border-zinc-800 text-zinc-500 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {source === "auto" && reviewCfg && (
        <div data-testid="review-coupon-settings" className="mt-6 border border-[#1f1f1f] bg-[#0a0a0a] p-5">
          <h3 className="font-display text-xs uppercase tracking-[0.2em]">Review reward settings</h3>
          <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
            Applies to every code generated from here on. A code is created when you approve a
            review. Codes are single use, expire on their own, and stay listed here for 30 days
            after being redeemed or expiring so you can look them up. Event Passes are excluded
            automatically.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-5">
            <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
              <input
                data-testid="review-coupon-enabled"
                type="checkbox"
                checked={reviewCfg.enabled}
                onChange={(e) => saveReviewCfg({ ...reviewCfg, enabled: e.target.checked })}
              />
              Feature on
            </label>
            <div>
              <label className={label}>Discount %</label>
              <input
                data-testid="review-coupon-percent"
                className={`${input} w-28`}
                type="number"
                step="0.5"
                value={reviewCfg.percent_off}
                onChange={(e) => setReviewCfg({ ...reviewCfg, percent_off: e.target.value })}
                onBlur={() => saveReviewCfg(reviewCfg)}
              />
            </div>
            <div>
              <label className={label}>Expires in (days)</label>
              <input
                data-testid="review-coupon-days"
                className={`${input} w-28`}
                type="number"
                value={reviewCfg.expiry_days}
                onChange={(e) => setReviewCfg({ ...reviewCfg, expiry_days: e.target.value })}
                onBlur={() => saveReviewCfg(reviewCfg)}
              />
            </div>
          </div>
        </div>
      )}

      {editing && (
        <form onSubmit={submit} data-testid="coupon-form" className="mt-8 border border-[#00ffcc]/30 bg-[#0a0a0a] p-5">
          <div className="grid gap-5 sm:grid-cols-3">
            <div>
              <label className={label}>Code</label>
              <input
                data-testid="coupon-code-input"
                className={input}
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                required
              />
            </div>
            <div>
              <label className={label}>Type</label>
              <select
                data-testid="coupon-type-select"
                className={input}
                value={form.discount_type}
                onChange={set("discount_type")}
              >
                <option value="percent">% off</option>
                <option value="fixed">$ off</option>
              </select>
            </div>
            <div>
              <label className={label}>{form.discount_type === "percent" ? "Percent off" : "Amount off ($)"}</label>
              <input
                data-testid="coupon-value-input"
                className={input}
                type="number"
                step="0.01"
                value={form.discount_type === "percent" ? form.percent_off : form.amount_off}
                onChange={set(form.discount_type === "percent" ? "percent_off" : "amount_off")}
                min="0.01"
                required
              />
            </div>
            <div>
              <label className={label}>Expires</label>
              <input
                data-testid="coupon-expiry-input"
                className={input}
                type="date"
                value={form.expires_at}
                onChange={set("expires_at")}
              />
            </div>
            <div>
              <label className={label}>Min cart ($)</label>
              <input
                data-testid="coupon-min-input"
                className={input}
                type="number"
                step="0.01"
                value={form.min_subtotal}
                onChange={set("min_subtotal")}
              />
            </div>
            <div>
              <label className={label}>Max total uses</label>
              <input
                data-testid="coupon-max-uses-input"
                className={input}
                type="number"
                value={form.max_uses}
                onChange={set("max_uses")}
              />
            </div>
            <div className="sm:col-span-3">
              <label className={label}>Also exclude these categories</label>
              <div className="flex flex-wrap gap-2">
                {categories
                  .filter((c) => c.key !== "event_pass")
                  .map((c) => (
                    <button
                      key={c.key}
                      type="button"
                      data-testid={`coupon-exclude-${c.key}`}
                      onClick={() => toggleExcluded(c.key)}
                      className={`border px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] ${
                        form.excluded_categories.includes(c.key)
                          ? "border-[#ff3b30] text-[#ff3b30]"
                          : "border-zinc-800 text-zinc-500 hover:text-white"
                      }`}
                    >
                      {c.label}
                    </button>
                  ))}
                <span className="border border-[#f4d03f]/50 px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-[#f4d03f]">
                  Event Passes · always excluded
                </span>
              </div>
            </div>
            <div className="sm:col-span-3 flex flex-wrap items-center gap-6">
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
                <input
                  data-testid="coupon-one-per-customer-toggle"
                  type="checkbox"
                  checked={form.one_per_customer}
                  onChange={set("one_per_customer")}
                />
                One per customer
              </label>
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
                <input data-testid="coupon-active-toggle" type="checkbox" checked={form.active} onChange={set("active")} />
                Active
              </label>
            </div>
          </div>
          <div className="mt-6 flex gap-3">
            <button
              data-testid="save-coupon-btn"
              disabled={busy}
              className="border border-[#00ffcc] px-6 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
            >
              {busy ? "Saving…" : "Save code"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(null)}
              className="border border-zinc-800 px-6 py-2 text-[10px] uppercase tracking-[0.25em] text-zinc-400 hover:text-white"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="mt-8 space-y-3" data-testid="coupons-list">
        {coupons.length === 0 && <p className="text-xs text-zinc-600">No discount codes yet.</p>}
        {coupons.map((c) => (
          <div
            key={c.id}
            data-testid={`coupon-row-${c.code}`}
            className="flex flex-wrap items-center gap-4 border border-[#1f1f1f] bg-[#0a0a0a] p-4"
          >
            <div className="min-w-[200px] flex-1">
              <p className="font-mono text-xs font-bold text-[#00ffcc]">{c.code}</p>
              <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                {c.discount_type === "percent" ? `${c.percent_off}% off` : `${money(c.amount_off)} off`}
                {c.min_subtotal ? ` · min ${money(c.min_subtotal)}` : ""}
                {c.max_uses ? ` · ${c.used_count}/${c.max_uses} used` : ` · ${c.used_count} used`}
                {c.one_per_customer ? " · 1 per customer" : ""}
                {c.expires_at ? ` · expires ${c.expires_at.slice(0, 10)}` : ""}
                {c.active ? "" : " · disabled"}
              </p>
              {c.source === "auto" && (
                <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                  issued to {c.issued_to || "—"} · review {c.review_id ? c.review_id.slice(-8) : "—"} ·
                  issued {c.created_at ? c.created_at.slice(0, 10) : "—"} ·{" "}
                  <span data-testid={`coupon-status-${c.code}`} className={autoStatus(c).tone}>
                    {autoStatus(c).label}
                  </span>
                </p>
              )}
            </div>
            <button
              data-testid={`edit-coupon-${c.code}`}
              onClick={() => open(c)}
              className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
            >
              <Pencil className="h-3 w-3" />
            </button>
            <button
              data-testid={`delete-coupon-${c.code}`}
              onClick={() => remove(c)}
              className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
