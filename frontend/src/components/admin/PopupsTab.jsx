import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { MessageSquarePlus, Trash2 } from "lucide-react";

import { api, apiError } from "@/lib/api";

const BLANK = {
  name: "New popup",
  type: "email_capture",
  enabled: true,
  title: "Get drop alerts & promos",
  body: "",
  button_label: "Join",
  dismiss_label: "Not now",
  collect_email: true,
  collect_name: false,
  trigger: "delay",
  delay_seconds: 10,
  page_views: 2,
  suppress_days: 14,
  paths: [],
  waitlist_product_id: "promo_list",
  coupon_percent_off: 5,
  coupon_prefix: "COMEBACK",
  coupon_expiry_days: 7,
  coupon_excluded_categories: ["event_pass"],
};

const field =
  "w-full bg-[#050505] px-3 py-2.5 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";

const PopupForm = ({ value, categories, onChange, onSave, onDelete, busy }) => {
  const set = (patch) => onChange({ ...value, ...patch });
  const isOffer = value.type === "discount_offer";

  return (
    <div
      data-testid={`popup-form-${value.id || "new"}`}
      className="border border-[#1f1f1f] bg-[#0a0a0a] p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <input
          data-testid="popup-name-field"
          value={value.name}
          onChange={(e) => set({ name: e.target.value })}
          className={`${field} max-w-xs`}
        />
        <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
          <input
            data-testid="popup-enabled-field"
            type="checkbox"
            checked={value.enabled}
            onChange={(e) => set({ enabled: e.target.checked })}
          />
          Enabled
        </label>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <label className={label}>Type</label>
          <select
            data-testid="popup-type-field"
            value={value.type}
            onChange={(e) => set({ type: e.target.value })}
            className={field}
          >
            <option value="email_capture">Email capture → waitlist</option>
            <option value="discount_offer">Discount offer → coupon</option>
          </select>
        </div>
        <div>
          <label className={label}>Trigger</label>
          <select
            data-testid="popup-trigger-field"
            value={value.trigger}
            onChange={(e) => set({ trigger: e.target.value })}
            className={field}
          >
            <option value="delay">After a delay</option>
            <option value="page_views">After N page views</option>
            <option value="exit_checkout">Leaving checkout unpaid</option>
          </select>
        </div>
        {value.trigger === "delay" && (
          <div>
            <label className={label}>Delay (seconds)</label>
            <input
              data-testid="popup-delay-field"
              type="number"
              min="1"
              value={value.delay_seconds}
              onChange={(e) => set({ delay_seconds: Number(e.target.value) })}
              className={field}
            />
          </div>
        )}
        {value.trigger === "page_views" && (
          <div>
            <label className={label}>Page views</label>
            <input
              data-testid="popup-pageviews-field"
              type="number"
              min="1"
              value={value.page_views}
              onChange={(e) => set({ page_views: Number(e.target.value) })}
              className={field}
            />
          </div>
        )}
        <div>
          <label className={label}>Don't show again for (days)</label>
          <input
            data-testid="popup-suppress-field"
            type="number"
            min="1"
            value={value.suppress_days}
            onChange={(e) => set({ suppress_days: Number(e.target.value) })}
            className={field}
          />
        </div>
        <div>
          <label className={label}>Only on these paths (blank = everywhere)</label>
          <input
            data-testid="popup-paths-field"
            value={value.paths.join(", ")}
            onChange={(e) =>
              set({ paths: e.target.value.split(",").map((p) => p.trim()).filter(Boolean) })
            }
            placeholder="/products, /"
            className={field}
          />
        </div>
      </div>

      <div className="mt-5 space-y-4">
        <div>
          <label className={label}>Headline</label>
          <input
            data-testid="popup-title-field"
            value={value.title}
            onChange={(e) => set({ title: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className={label}>Body text</label>
          <textarea
            data-testid="popup-body-field"
            rows={2}
            value={value.body}
            onChange={(e) => set({ body: e.target.value })}
            className={field}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={label}>Button label</label>
            <input
              data-testid="popup-button-field"
              value={value.button_label}
              onChange={(e) => set({ button_label: e.target.value })}
              className={field}
            />
          </div>
          <div>
            <label className={label}>Dismiss label</label>
            <input
              data-testid="popup-dismiss-field"
              value={value.dismiss_label}
              onChange={(e) => set({ dismiss_label: e.target.value })}
              className={field}
            />
          </div>
        </div>
      </div>

      {!isOffer && (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <label className={label}>Waitlist bucket id</label>
            <input
              data-testid="popup-bucket-field"
              value={value.waitlist_product_id}
              onChange={(e) => set({ waitlist_product_id: e.target.value })}
              className={field}
            />
          </div>
          <div className="flex items-end gap-5 pb-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
            <label className="flex items-center gap-2">
              <input
                data-testid="popup-collect-email-field"
                type="checkbox"
                checked={value.collect_email}
                onChange={(e) => set({ collect_email: e.target.checked })}
              />
              Email
            </label>
            <label className="flex items-center gap-2">
              <input
                data-testid="popup-collect-name-field"
                type="checkbox"
                checked={value.collect_name}
                onChange={(e) => set({ collect_name: e.target.checked })}
              />
              First name
            </label>
          </div>
        </div>
      )}

      {isOffer && (
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <div>
            <label className={label}>Percent off</label>
            <input
              data-testid="popup-percent-field"
              type="number"
              min="1"
              max="100"
              value={value.coupon_percent_off}
              onChange={(e) => set({ coupon_percent_off: Number(e.target.value) })}
              className={field}
            />
          </div>
          <div>
            <label className={label}>Code prefix</label>
            <input
              data-testid="popup-prefix-field"
              value={value.coupon_prefix}
              onChange={(e) => set({ coupon_prefix: e.target.value.toUpperCase() })}
              className={field}
            />
          </div>
          <div>
            <label className={label}>Code expires in (days)</label>
            <input
              data-testid="popup-expiry-field"
              type="number"
              min="1"
              value={value.coupon_expiry_days}
              onChange={(e) => set({ coupon_expiry_days: Number(e.target.value) })}
              className={field}
            />
          </div>
          <div className="sm:col-span-3">
            <label className={label}>Excluded categories</label>
            <div className="flex flex-wrap gap-3">
              {categories.map((c) => {
                const on = value.coupon_excluded_categories.includes(c.key);
                return (
                  <label
                    key={c.key}
                    className="flex items-center gap-2 border border-zinc-800 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400"
                  >
                    <input
                      data-testid={`popup-exclude-${c.key}`}
                      type="checkbox"
                      checked={on}
                      onChange={(e) =>
                        set({
                          coupon_excluded_categories: e.target.checked
                            ? [...value.coupon_excluded_categories, c.key]
                            : value.coupon_excluded_categories.filter((k) => k !== c.key),
                        })
                      }
                    />
                    {c.label}
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="mt-6 flex gap-3">
        <button
          data-testid={`popup-save-${value.id || "new"}`}
          disabled={busy}
          onClick={onSave}
          className="border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
        >
          {busy ? "Saving…" : value.id ? "Save changes" : "Create popup"}
        </button>
        {value.id && (
          <button
            data-testid={`popup-delete-${value.id}`}
            onClick={onDelete}
            className="flex items-center gap-2 border border-zinc-800 px-4 py-3 text-[10px] uppercase tracking-[0.25em] text-zinc-500 transition-colors hover:border-[#ff3b30] hover:text-[#ff3b30]"
          >
            <Trash2 className="h-3 w-3" /> Delete
          </button>
        )}
      </div>
    </div>
  );
};

export const PopupsTab = ({ categories = [] }) => {
  const [rows, setRows] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      api
        .get("/admin/popups")
        .then(({ data }) => setRows(data))
        .catch((e) => {
          toast.error(apiError(e));
          setRows([]);
        }),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  const save = async (popup) => {
    const { id, ...body } = popup;
    setBusy(true);
    try {
      if (id) await api.put(`/admin/popups/${id}`, body);
      else await api.post("/admin/popups", body);
      toast.success(id ? "Popup updated" : "Popup created");
      setDraft(null);
      load();
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (popup) => {
    if (!window.confirm(`Delete "${popup.name}"?`)) return;
    try {
      await api.delete(`/admin/popups/${popup.id}`);
      toast.success("Popup deleted");
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  if (!rows) return <p className="py-16 text-xs text-zinc-600">Loading popups…</p>;

  return (
    <div data-testid="popups-tab" className="mt-10 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[10px] leading-relaxed text-zinc-600">
          Everything about each popup — text, trigger, timing, what it collects and the coupon it
          hands out — is editable here. Email captures land in Waitlist; offers mint a real
          single-use code.
        </p>
        <button
          data-testid="new-popup-btn"
          onClick={() => setDraft({ ...BLANK })}
          className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
        >
          <MessageSquarePlus className="h-3 w-3" /> New popup
        </button>
      </div>

      {draft && (
        <PopupForm
          value={draft}
          categories={categories}
          onChange={setDraft}
          onSave={() => save(draft)}
          busy={busy}
        />
      )}

      {rows.map((r) => (
        <PopupForm
          key={r.id}
          value={r}
          categories={categories}
          onChange={(next) => setRows((prev) => prev.map((p) => (p.id === r.id ? next : p)))}
          onSave={() => save(r)}
          onDelete={() => remove(r)}
          busy={busy}
        />
      ))}

      {rows.length === 0 && !draft && (
        <p data-testid="popups-empty" className="text-xs text-zinc-600">
          No popups yet.
        </p>
      )}
    </div>
  );
};
