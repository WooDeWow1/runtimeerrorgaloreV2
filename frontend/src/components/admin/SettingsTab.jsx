import { useState } from "react";
import { BarChart3, KeyRound, Megaphone } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";

const BannerForm = ({ banner, setBanner, bannerLoaded }) => {
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.put("/admin/settings/banner", banner);
      toast.success("Banner saved — reload any page to see it");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={save}
      data-testid="banner-form"
      className="space-y-4 border border-[#1f1f1f] bg-[#0a0a0a] p-6 lg:col-span-12"
    >
      <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
        <Megaphone className="h-4 w-4 text-[#00ffcc]" /> Announcement banner
      </h2>
      <fieldset disabled={!bannerLoaded} className="space-y-4 disabled:opacity-50">
      {!bannerLoaded && (
        <p data-testid="banner-loading" className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
          Loading current banner…
        </p>
      )}
      <p className="text-[10px] leading-relaxed text-zinc-600">
        Shows at the very top of every page. Leave it off until you have something to promote.
      </p>
      <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
        <input
          data-testid="banner-enabled-checkbox"
          type="checkbox"
          checked={banner.enabled}
          onChange={(e) => setBanner({ ...banner, enabled: e.target.checked })}
        />
        Show banner
      </label>
      <div>
        <label className={label}>Message</label>
        <input
          data-testid="banner-text-input"
          className={input}
          maxLength={120}
          value={banner.text}
          onChange={(e) => setBanner({ ...banner, text: e.target.value })}
          placeholder="Community Day weekend — 15% off all coin bundles"
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={label}>Link (optional)</label>
          <input
            data-testid="banner-link-input"
            className={input}
            value={banner.link_url}
            onChange={(e) => setBanner({ ...banner, link_url: e.target.value })}
            placeholder="/products"
          />
        </div>
        <div>
          <label className={label}>Link label</label>
          <input
            data-testid="banner-link-label-input"
            className={input}
            maxLength={30}
            value={banner.link_label}
            onChange={(e) => setBanner({ ...banner, link_label: e.target.value })}
            placeholder="Shop now"
          />
        </div>
      </div>
      <button
        data-testid="save-banner-btn"
        disabled={busy || !bannerLoaded}
        className="border border-[#00ffcc] px-8 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save banner"}
      </button>
      </fieldset>
    </form>
  );
};

const PasswordForm = () => {
  const [pwd, setPwd] = useState({ current_password: "", new_password: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pwd.new_password !== pwd.confirm) {
      toast.error("New passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: pwd.current_password,
        new_password: pwd.new_password,
      });
      toast.success("Password updated", { description: "Use your new password next time you sign in." });
      setPwd({ current_password: "", new_password: "", confirm: "" });
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      data-testid="password-form"
      className="space-y-4 border border-[#1f1f1f] bg-[#0a0a0a] p-6 lg:col-span-5"
    >
      <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
        <KeyRound className="h-4 w-4 text-[#00ffcc]" /> Admin password
      </h2>
      <div>
        <label className={label}>Current password</label>
        <input data-testid="current-password-input" className={input} type="password" required
               autoComplete="current-password" value={pwd.current_password}
               onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} />
      </div>
      <div>
        <label className={label}>New password (min 8 chars)</label>
        <input data-testid="new-password-input" className={input} type="password" required minLength={8}
               autoComplete="new-password" value={pwd.new_password}
               onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} />
      </div>
      <div>
        <label className={label}>Confirm new password</label>
        <input data-testid="confirm-password-input" className={input} type="password" required minLength={8}
               autoComplete="new-password" value={pwd.confirm}
               onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} />
      </div>
      <button
        data-testid="save-password-btn"
        disabled={busy}
        className="w-full border border-[#00ffcc] py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
      >
        {busy ? "Updating…" : "Update password"}
      </button>
      <p className="text-[10px] leading-relaxed text-zinc-600">
        Hashed with bcrypt before storage. Once changed here, the value stays put and is no longer
        overwritten by the seed variables on restart.
      </p>
    </form>
  );
};

const Analytics = ({ stats, reload }) => (
  <div className="space-y-8 lg:col-span-7">
    <div>
      <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
        <BarChart3 className="h-4 w-4 text-[#00ffcc]" /> Traffic
      </h2>
      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3">
        {[
          ["Unique visitors", stats?.totals.unique_visitors],
          ["Visits today", stats?.totals.visits_today],
          ["Page hits", stats?.totals.total_hits],
          ["Orders", stats?.totals.orders],
          ["Revenue", stats ? money(stats.totals.revenue) : null],
          ["Waitlist", stats?.totals.waitlist],
        ].map(([k, v]) => (
          <div key={k} data-testid={`stat-${k.toLowerCase().replace(/ /g, "-")}`}
               className="border border-[#1f1f1f] bg-[#0a0a0a] p-4">
            <p className="font-display text-xl text-[#00ffcc]">{v ?? "—"}</p>
            <p className="mt-1 text-[9px] uppercase tracking-[0.2em] text-zinc-500">{k}</p>
          </div>
        ))}
      </div>
    </div>

    {stats?.top_countries?.length > 0 && (
      <div className="flex flex-wrap gap-3" data-testid="top-countries">
        {stats.top_countries.map((c) => (
          <span key={c.country} className="border border-zinc-800 px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
            {c.country} · {c.visitors}
          </span>
        ))}
      </div>
    )}

    <div className="border border-[#1f1f1f] bg-[#0a0a0a]" data-testid="visitors-table">
      <div className="flex items-center justify-between border-b border-[#1f1f1f] px-5 py-3">
        <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">Recent visitors</p>
        <button data-testid="refresh-analytics-btn" onClick={reload}
                className="text-[9px] uppercase tracking-[0.2em] text-zinc-500 hover:text-[#00ffcc]">
          Refresh
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-[9px] uppercase tracking-[0.2em] text-zinc-600">
              <th className="px-5 py-3 font-normal">Visitor IP</th>
              <th className="px-5 py-3 font-normal">Date / time</th>
              <th className="px-5 py-3 font-normal">Country</th>
              <th className="px-5 py-3 font-normal">Hits</th>
            </tr>
          </thead>
          <tbody>
            {(stats?.visits || []).map((v) => (
              <tr key={`${v.ip}-${v.last_seen}`} data-testid="visitor-row" className="border-t border-zinc-900">
                <td className="px-5 py-3 font-mono text-[#00ffcc]">{v.ip}</td>
                <td className="px-5 py-3 text-zinc-400">
                  {v.last_seen ? new Date(v.last_seen).toLocaleString() : "—"}
                </td>
                <td className="px-5 py-3 text-zinc-300">{v.country}</td>
                <td className="px-5 py-3 text-zinc-500">{v.hits}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {stats && stats.visits.length === 0 && (
          <p data-testid="no-visitors" className="px-5 py-6 text-xs text-zinc-600">No visits logged yet.</p>
        )}
      </div>
    </div>
    <p className="text-[10px] leading-relaxed text-zinc-600">
      One row per IP per day (hits counted), country cached per IP via ip-api.com, rows auto-expire after
      90 days — keeps the collection tiny.
    </p>
  </div>
);

export const SettingsTab = ({ banner, setBanner, bannerLoaded, stats, reloadStats }) => (
  <div className="mt-10 grid gap-10 lg:grid-cols-12">
    <BannerForm banner={banner} setBanner={setBanner} bannerLoaded={bannerLoaded} />
    <PasswordForm />
    <Analytics stats={stats} reload={reloadStats} />
  </div>
);
