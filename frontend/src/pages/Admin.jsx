import { useEffect, useState } from "react";
import { BarChart3, Eye, KeyRound, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, CATEGORY_LABELS, money, STATUS_LABELS } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";
const EMPTY = {
  name: "", description: "", category: "pokecoin_bundle", price: "", msrp: "", image_url: "",
  coins: "", badge: "", active: true, coming_soon: false,
};

export default function Admin() {
  const [tab, setTab] = useState("orders");
  const [orders, setOrders] = useState([]);
  const [products, setProducts] = useState([]);
  const [creds, setCreds] = useState({});
  const [openOrder, setOpenOrder] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [pwd, setPwd] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwdBusy, setPwdBusy] = useState(false);
  const [stats, setStats] = useState(null);

  const loadOrders = () => api.get("/admin/orders").then(({ data }) => setOrders(data)).catch(() => {});
  const loadProducts = () =>
    api.get("/products", { params: { include_inactive: true } }).then(({ data }) => setProducts(data)).catch(() => {});
  const loadStats = () => api.get("/admin/analytics").then(({ data }) => setStats(data)).catch(() => {});

  useEffect(() => {
    loadOrders();
    loadProducts();
  }, []);

  useEffect(() => {
    if (tab === "settings") loadStats();
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

  const set = (k) => (e) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const saveProduct = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      price: parseFloat(form.price),
      msrp: form.msrp === "" ? null : parseFloat(form.msrp),
      coins: form.coins === "" ? null : parseInt(form.coins, 10),
    };
    try {
      if (editing) await api.put(`/products/${editing}`, payload);
      else await api.post("/products", payload);
      toast.success(editing ? "Product updated" : "Product created");
      setForm(EMPTY);
      setEditing(null);
      loadProducts();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const editProduct = (p) => {
    setEditing(p.id);
    setForm({
      name: p.name, description: p.description, category: p.category, price: String(p.price),
      msrp: p.msrp ?? "", image_url: p.image_url || "", coins: p.coins ?? "", badge: p.badge || "",
      active: p.active, coming_soon: p.coming_soon,
    });
    setTab("products");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const removeProduct = async (id) => {
    try {
      await api.delete(`/products/${id}`);
      toast.success("Product removed");
      loadProducts();
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

  return (
    <div data-testid="admin-page" className="mx-auto max-w-[1400px] px-5 py-14 lg:px-10 lg:py-20">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// operator console</p>
      <h1 className="mt-4 font-display text-3xl tracking-tighter">Admin</h1>

      <div className="mt-10 flex flex-wrap gap-3">
        {[
          { key: "orders", label: "orders" },
          { key: "products", label: "products" },
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
                  <p className="mt-1 text-xs text-[#00ffcc]">{money(o.total)} · payment {o.payment_status}</p>
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
        <div className="mt-10 grid gap-10 lg:grid-cols-12">
          <form
            onSubmit={saveProduct}
            data-testid="product-form"
            className="space-y-4 border border-[#1f1f1f] bg-[#0a0a0a] p-6 lg:col-span-5"
          >
            <h2 className="font-display text-sm uppercase tracking-[0.2em]">
              {editing ? "Edit product" : "New product"}
            </h2>
            <div>
              <label className={label}>Name</label>
              <input data-testid="product-name-input" className={input} value={form.name} onChange={set("name")} required />
            </div>
            <div>
              <label className={label}>Description</label>
              <textarea data-testid="product-description-input" className={input} rows={3} value={form.description} onChange={set("description")} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={label}>Category</label>
                <select data-testid="product-category-select" className={input} value={form.category} onChange={set("category")}>
                  {Object.entries(CATEGORY_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={label}>Price (USD)</label>
                <input data-testid="product-price-input" className={input} type="number" step="0.01" min="0.5"
                       value={form.price} onChange={set("price")} required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={label}>MSRP (optional)</label>
                <input data-testid="product-msrp-input" className={input} type="number" step="0.01" min="0.5"
                       value={form.msrp} onChange={set("msrp")} />
              </div>
              <div>
                <label className={label}>Coins (optional)</label>
                <input data-testid="product-coins-input" className={input} type="number" value={form.coins} onChange={set("coins")} />
              </div>
            </div>
            <div>
              <label className={label}>Badge</label>
              <input data-testid="product-badge-input" className={input} value={form.badge} onChange={set("badge")} />
            </div>
            <div>
              <label className={label}>Image URL</label>
              <input data-testid="product-image-input" className={input} value={form.image_url} onChange={set("image_url")} />
            </div>
            <div className="flex gap-6 pt-2">
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
                <input data-testid="product-active-checkbox" type="checkbox" checked={form.active} onChange={set("active")} />
                Active
              </label>
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
                <input data-testid="product-coming-soon-checkbox" type="checkbox" checked={form.coming_soon} onChange={set("coming_soon")} />
                Coming soon
              </label>
            </div>
            <div className="flex gap-3 pt-2">
              <button
                data-testid="save-product-btn"
                className="flex flex-1 items-center justify-center gap-2 border border-[#00ffcc] py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
              >
                <Plus className="h-3 w-3" /> {editing ? "Update" : "Create"}
              </button>
              {editing && (
                <button
                  type="button"
                  data-testid="cancel-edit-btn"
                  onClick={() => { setEditing(null); setForm(EMPTY); }}
                  className="border border-zinc-800 px-5 text-[10px] uppercase tracking-[0.25em] text-zinc-400"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>

          <div className="space-y-4 lg:col-span-7" data-testid="admin-products-list">
            {products.map((p) => (
              <div key={p.id} data-testid={`admin-product-${p.id}`} className="flex items-center gap-4 border border-[#1f1f1f] bg-[#0a0a0a] p-4">
                {p.image_url && <img src={p.image_url} alt={p.name} className="h-14 w-14 object-cover" />}
                <div className="flex-1">
                  <p className="text-xs font-bold">{p.name}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                    {CATEGORY_LABELS[p.category]} · {money(p.price)} {p.active ? "" : "· inactive"}
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
                <button data-testid={`edit-product-${p.id}`} onClick={() => editProduct(p)}
                        className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]">
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button data-testid={`delete-product-${p.id}`} onClick={() => removeProduct(p.id)}
                        className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#ff3b30] hover:text-[#ff3b30]">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "settings" && (
        <div className="mt-10 grid gap-10 lg:grid-cols-12">
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
