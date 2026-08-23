import { useEffect, useState } from "react";
import { BarChart3, Download, Eye, KeyRound, Megaphone, Star, UploadCloud, Users } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, CATEGORY_LABELS, money, STATUS_LABELS } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";
export default function Admin() {
  const [tab, setTab] = useState("orders");
  const [orders, setOrders] = useState([]);
  const [products, setProducts] = useState([]);
  const [creds, setCreds] = useState({});
  const [openOrder, setOpenOrder] = useState(null);
  const [pwd, setPwd] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwdBusy, setPwdBusy] = useState(false);
  const [stats, setStats] = useState(null);
  const [waitlist, setWaitlist] = useState([]);
  const [banner, setBanner] = useState({ enabled: false, text: "", link_url: "", link_label: "" });
  const [bannerBusy, setBannerBusy] = useState(false);
  const [waitlistQuery, setWaitlistQuery] = useState("");
  const [sync, setSync] = useState(null);
  const [syncBusy, setSyncBusy] = useState(false);

  const checkSync = async () => {
    setSyncBusy(true);
    try {
      const { data } = await api.get("/admin/sync/catalog");
      setSync(data);
      const pending = data.creates.length + data.updates.length;
      toast.success(pending ? `${pending} change(s) ready to push` : "Production already matches preview");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSyncBusy(false);
    }
  };

  const pushSync = async () => {
    setSyncBusy(true);
    try {
      const { data } = await api.post("/admin/sync/catalog");
      setSync(data);
      if (data.errors.length) toast.error(`Pushed with ${data.errors.length} error(s)`);
      else toast.success("Production catalog updated");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSyncBusy(false);
    }
  };

  const loadWaitlist = () =>
    api.get("/admin/waitlist").then(({ data }) => setWaitlist(data)).catch(() => {});

  const productName = (id) => products.find((p) => p.id === id)?.name || "General";

  const filteredWaitlist = waitlist.filter((w) => {
    const q = waitlistQuery.trim().toLowerCase();
    if (!q) return true;
    return w.email.toLowerCase().includes(q) || productName(w.product_id).toLowerCase().includes(q);
  });

  const exportWaitlist = () => {
    const rows = [
      ["email", "source", "signed_up"],
      ...filteredWaitlist.map((w) => [
        w.email,
        productName(w.product_id),
        w.created_at ? new Date(w.created_at).toISOString() : "",
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `waitlist-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };


  const loadOrders = () => api.get("/admin/orders").then(({ data }) => setOrders(data)).catch(() => {});
  const loadProducts = () =>
    api.get("/products", { params: { include_inactive: true } }).then(({ data }) => setProducts(data)).catch(() => {});
  const loadStats = () => api.get("/admin/analytics").then(({ data }) => setStats(data)).catch(() => {});

  useEffect(() => {
    loadOrders();
    loadProducts();
  }, []);

  useEffect(() => {
    if (tab === "settings") {
      loadStats();
      api.get("/settings/banner").then(({ data }) => setBanner(data)).catch(() => {});
    }
    if (tab === "waitlist") loadWaitlist();
  }, [tab]);

  const changePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password !== pwd.confirm) {
      toast.error("New passwords do not match");
      return;
    }
    setPwdBusy(true);
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
      setPwdBusy(false);
    }
  };

  const setStatus = async (id, status) => {
    try {
      await api.patch(`/admin/orders/${id}/status`, { status });
      toast.success(`Order marked ${STATUS_LABELS[status]}`);
      loadOrders();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const reveal = async (id) => {
    try {
      const { data } = await api.get(`/admin/orders/${id}/credentials`);
      setCreds((prev) => ({ ...prev, [id]: data }));
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const toggleFeatured = async (product) => {
    const next = !product.is_featured;
    setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, is_featured: next } : p)));
    try {
      await api.patch(`/products/${product.id}/featured`, { is_featured: next });
      toast.success(next ? `${product.name} featured on the home page` : `${product.name} unfeatured`);
    } catch (e) {
      setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, is_featured: !next } : p)));
      toast.error(apiError(e));
    }
  };

  const toggleComingSoon = async (product) => {
    const next = !product.coming_soon;
    setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, coming_soon: next } : p)));
    try {
      await api.put(`/products/${product.id}`, { coming_soon: next });
      toast.success(next ? `${product.name} marked Coming Soon` : `${product.name} is on sale`);
    } catch (e) {
      setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, coming_soon: !next } : p)));
      toast.error(apiError(e));
    }
  };

  const saveBanner = async (e) => {
    e.preventDefault();
    setBannerBusy(true);
    try {
      await api.put("/admin/settings/banner", banner);
      toast.success("Banner saved — reload any page to see it");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBannerBusy(false);
    }
  };

  return (
    <div data-testid="admin-page" className="mx-auto max-w-[1400px] px-5 py-14 lg:px-10 lg:py-20">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// operator console</p>
      <h1 className="mt-4 font-display text-3xl tracking-tighter">Admin</h1>

      <div className="mt-10 flex flex-wrap gap-3">
        {[
          { key: "orders", label: "orders" },
          { key: "products", label: "products" },
          { key: "waitlist", label: "waitlist" },
          { key: "settings", label: "settings & analytics" },
        ].map((t) => (
          <button
            key={t.key}
            data-testid={`admin-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`border px-5 py-2 text-[10px] uppercase tracking-[0.25em] transition-colors ${
              tab === t.key ? "border-[#00ffcc] text-[#00ffcc]" : "border-zinc-800 text-zinc-500 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "orders" && (
        <div className="mt-10 space-y-5" data-testid="admin-orders-list">
          {orders.length === 0 && <p className="text-xs text-zinc-600">No orders yet.</p>}
          {orders.map((o) => (
            <div key={o.id} data-testid={`admin-order-${o.id}`} className="border border-[#1f1f1f] bg-[#0a0a0a] p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                    #{o.id.slice(-8)} · {o.user_email}
                  </p>
                  <p className="mt-2 text-xs text-zinc-300">
                    {o.items.map((i) => `${i.name} ×${i.quantity}`).join(" · ")}
                  </p>
          <p className="mt-1 text-xs text-[#00ffcc]">
            {money(o.total)}
            {o.discount > 0 && (
              <span className="text-zinc-500">
                {" "}· {o.coupon_code} -{money(o.discount)}
              </span>
            )}
            {" "}· payment {o.payment_status}
          </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge status={o.status} testId={`admin-order-status-${o.id}`} />
                  {["pending", "processing", "completed", "cancelled"].map((s) => (
                    <button
                      key={s}
                      data-testid={`set-status-${s}-${o.id}`}
                      onClick={() => setStatus(o.id, s)}
                      className="border border-zinc-800 px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-4 border-t border-zinc-900 pt-4">
                <button
                  data-testid={`reveal-creds-${o.id}`}
                  onClick={() => reveal(o.id)}
                  className="flex items-center gap-2 border border-[#9966cc] px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-[#9966cc] transition-colors hover:bg-[#9966cc] hover:text-black"
                >
                  <Eye className="h-3 w-3" /> Reveal PTC
                </button>
                {creds[o.id] && (
                  <span data-testid={`creds-${o.id}`} className="border border-zinc-800 bg-black px-3 py-1.5 font-mono text-[11px] text-[#00ffcc]">
                    {creds[o.id].ptc_username} / {creds[o.id].ptc_password}
                  </span>
                )}
                <button
                  data-testid={`toggle-chat-${o.id}`}
                  onClick={() => setOpenOrder(openOrder === o.id ? null : o.id)}
                  className="border border-zinc-800 px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
                >
                  {openOrder === o.id ? "Hide chat" : "Open chat"}
                </button>
              </div>

              {openOrder === o.id && (
                <div className="mt-5">
                  <OrderChat orderId={o.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "products" && (
        <div className="mt-10" data-testid="admin-products-list">
          <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-5" data-testid="catalog-sync-panel">
            <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
              <UploadCloud className="h-4 w-4 text-[#00ffcc]" /> Push catalog live
            </h2>
            <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
              Copies this catalog — names, images, SellAuth ids, featured stars and Coming Soon flags —
              to the live site. Check first, then push. Nothing is ever deleted from production.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                data-testid="sync-check-btn"
                disabled={syncBusy}
                onClick={checkSync}
                className="border border-zinc-800 px-5 py-2 text-[10px] uppercase tracking-[0.25em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc] disabled:opacity-40"
              >
                {syncBusy ? "Working…" : "Check differences"}
              </button>
              <button
                data-testid="sync-push-btn"
                disabled={syncBusy || !sync || sync.creates.length + sync.updates.length === 0}
                onClick={pushSync}
                className="border border-[#00ffcc] px-5 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-30"
              >
                Push to production
              </button>
            </div>

            {sync && (
              <div className="mt-5 border-t border-zinc-900 pt-4 text-[10px]" data-testid="sync-result">
                <p className="text-zinc-500">
                  {sync.target} · preview {sync.source_count} products · production {sync.target_count}
                  {sync.applied ? " · pushed" : ""}
                </p>
                {sync.creates.length === 0 && sync.updates.length === 0 && (
                  <p className="mt-2 text-[#00ffcc]">In sync — nothing to push.</p>
                )}
                {sync.creates.map((c) => (
                  <p key={c.name} className="mt-2 text-zinc-300">
                    <span className="text-[#00ffcc]">NEW</span> {c.name} · {CATEGORY_LABELS[c.category] || c.category} · {money(c.price)}
                  </p>
                ))}
                {sync.updates.map((u) => (
                  <p key={u.name} className="mt-2 text-zinc-300">
                    <span className="text-[#f4d03f]">EDIT</span> {u.name} ·{" "}
                    <span className="text-zinc-500">{Object.keys(u.changes).join(", ")}</span>
                  </p>
                ))}
                {sync.errors.map((e) => (
                  <p key={e} className="mt-2 text-red-400">{e}</p>
                ))}
              </div>
            )}
          </div>

          <p className="mt-8 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
            Pricing, stock and discount codes now live in SellAuth. Here you control how each product
            looks on the site: star it for the home page, or flag it Coming Soon (visible, unbuyable,
            collects waitlist signups).
          </p>
          <div className="mt-8 space-y-4">
            {products.map((p) => (
              <div key={p.id} data-testid={`admin-product-${p.id}`} className="flex flex-wrap items-center gap-4 border border-[#1f1f1f] bg-[#0a0a0a] p-4">
                {p.image_url && <img src={p.image_url} alt={p.name} className="h-14 w-14 object-cover" />}
                <div className="min-w-[200px] flex-1">
                  <p className="text-xs font-bold">{p.name}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                    {CATEGORY_LABELS[p.category]} · {money(p.price)}
                    {p.sellauth_product_id ? ` · SA ${p.sellauth_product_id}` : " · not in SellAuth"}
                    {p.coming_soon ? " · soon" : ""}
                    {p.is_featured ? " · featured" : ""}
                  </p>
                </div>
                <button
                  data-testid={`toggle-featured-${p.id}`}
                  aria-pressed={p.is_featured}
                  title={p.is_featured ? "Remove from home page" : "Feature on home page"}
                  onClick={() => toggleFeatured(p)}
                  className={`border p-2 transition-colors ${
                    p.is_featured
                      ? "border-[#f4d03f] text-[#f4d03f]"
                      : "border-zinc-800 text-zinc-500 hover:border-[#f4d03f] hover:text-[#f4d03f]"
                  }`}
                >
                  <Star className="h-3.5 w-3.5" fill={p.is_featured ? "currentColor" : "none"} />
                </button>
                <button
                  data-testid={`toggle-coming-soon-${p.id}`}
                  aria-pressed={p.coming_soon}
                  onClick={() => toggleComingSoon(p)}
                  className={`border px-4 py-2 text-[10px] uppercase tracking-[0.2em] transition-colors ${
                    p.coming_soon
                      ? "border-[#9966cc] text-[#c7a6f0]"
                      : "border-zinc-800 text-zinc-500 hover:border-[#9966cc] hover:text-[#c7a6f0]"
                  }`}
                >
                  {p.coming_soon ? "Coming soon" : "On sale"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "waitlist" && (
        <div className="mt-10" data-testid="waitlist-panel">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
                <Users className="h-4 w-4 text-[#00ffcc]" /> Waitlist
                <span className="text-zinc-500">· {waitlist.length}</span>
              </h2>
              <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
                Everyone who asked to be notified when a coming-soon drop goes live.
              </p>
            </div>
            <div className="flex gap-2">
              <input
                data-testid="waitlist-search-input"
                className={`${input} w-52`}
                placeholder="Search email or product"
                value={waitlistQuery}
                onChange={(e) => setWaitlistQuery(e.target.value)}
              />
              <button
                data-testid="waitlist-export-btn"
                onClick={exportWaitlist}
                disabled={filteredWaitlist.length === 0}
                className="flex items-center gap-2 border border-[#00ffcc] px-4 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
              >
                <Download className="h-3 w-3" /> CSV
              </button>
            </div>
          </div>

          <div className="mt-8 space-y-3" data-testid="waitlist-list">
            {filteredWaitlist.length === 0 && (
              <p data-testid="waitlist-empty" className="text-xs text-zinc-600">
                No waitlist signups yet.
              </p>
            )}
            {filteredWaitlist.map((w) => (
              <div
                key={`${w.email}-${w.product_id}`}
                data-testid={`waitlist-row-${w.email}`}
                className="flex flex-wrap items-center justify-between gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-4"
              >
                <div>
                  <p className="font-mono text-xs text-white">{w.email}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                    {productName(w.product_id)}
                  </p>
                </div>
                <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                  {w.created_at ? new Date(w.created_at).toLocaleString() : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "settings" && (
        <div className="mt-10 grid gap-10 lg:grid-cols-12">
          <form
            onSubmit={saveBanner}
            data-testid="banner-form"
            className="space-y-4 border border-[#1f1f1f] bg-[#0a0a0a] p-6 lg:col-span-12"
          >
            <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
              <Megaphone className="h-4 w-4 text-[#00ffcc]" /> Announcement banner
            </h2>
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
              disabled={bannerBusy}
              className="border border-[#00ffcc] px-8 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
            >
              {bannerBusy ? "Saving…" : "Save banner"}
            </button>
          </form>

          <form
            onSubmit={changePassword}
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
              disabled={pwdBusy}
              className="w-full border border-[#00ffcc] py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
            >
              {pwdBusy ? "Updating…" : "Update password"}
            </button>
            <p className="text-[10px] leading-relaxed text-zinc-600">
              Hashed with bcrypt before storage. Once changed here, the value stays put and is no longer
              overwritten by the seed variables on restart.
            </p>
          </form>

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
                <button data-testid="refresh-analytics-btn" onClick={loadStats}
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
              One row per IP per day (hits counted), country cached per IP via ip-api.com, rows auto-expire
              after 90 days — keeps the collection tiny.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
