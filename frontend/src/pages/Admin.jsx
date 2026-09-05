import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, apiError, STATUS_LABELS } from "@/lib/api";
import { useCategories } from "@/lib/useCategories";
import { CategoriesTab } from "@/components/admin/CategoriesTab";
import { CouponsTab } from "@/components/admin/CouponsTab";
import { OrdersTab } from "@/components/admin/OrdersTab";
import { ProductsTab } from "@/components/admin/ProductsTab";
import { ReviewsTab } from "@/components/admin/ReviewsTab";
import { SettingsTab } from "@/components/admin/SettingsTab";
import { WaitlistTab } from "@/components/admin/WaitlistTab";

const TABS = [
  { key: "orders", label: "orders" },
  { key: "products", label: "products" },
  { key: "categories", label: "categories" },
  { key: "coupons", label: "discount codes" },
  { key: "reviews", label: "reviews" },
  { key: "waitlist", label: "waitlist" },
  { key: "settings", label: "settings & analytics" },
];

const EMPTY_BANNER = { enabled: false, text: "", link_url: "", link_label: "" };

export default function Admin() {
  const [tab, setTab] = useState("orders");
  const [orders, setOrders] = useState([]);
  const [products, setProducts] = useState([]);
  const [creds, setCreds] = useState({});
  const [openOrder, setOpenOrder] = useState(null);
  const [stats, setStats] = useState(null);
  const [waitlist, setWaitlist] = useState([]);
  const [banner, setBanner] = useState(EMPTY_BANNER);
  const [bannerLoaded, setBannerLoaded] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null); // null | "new" | product
  const [unread, setUnread] = useState({ orders: 0, messages: 0 });
  const [sync, setSync] = useState(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const { categories, labelOf, reload: reloadCategories } = useCategories();

  const loadOrders = useCallback(
    () => api.get("/admin/orders").then(({ data }) => setOrders(data)).catch(() => {}),
    []
  );
  const loadProducts = useCallback(
    () =>
      api
        .get("/products", { params: { include_inactive: true } })
        .then(({ data }) => setProducts(data))
        .catch(() => {}),
    []
  );
  const loadStats = useCallback(
    () => api.get("/admin/analytics").then(({ data }) => setStats(data)).catch(() => {}),
    []
  );
  const loadWaitlist = useCallback(
    () => api.get("/admin/waitlist").then(({ data }) => setWaitlist(data)).catch(() => {}),
    []
  );
  const loadUnread = useCallback(
    () => api.get("/admin/unread").then(({ data }) => setUnread(data)).catch(() => {}),
    []
  );

  const openOrderRef = useRef(null);
  openOrderRef.current = openOrder;
  const deepLinked = useRef(false);

  const openChat = useCallback(
    async (orderId, { toggle = true } = {}) => {
      const alreadyOpen = toggle && openOrderRef.current === orderId;
      setOpenOrder(alreadyOpen ? null : orderId);
      if (alreadyOpen) return;
      try {
        await api.post(`/admin/orders/${orderId}/read`);
        loadOrders();
        loadUnread();
      } catch {
        // Clearing the unread flag is best-effort; the chat still opens.
      }
    },
    [loadOrders, loadUnread]
  );

  useEffect(() => {
    loadOrders();
    loadProducts();
    loadUnread();
    const timer = setInterval(loadUnread, 15000);
    return () => clearInterval(timer);
  }, [loadOrders, loadProducts, loadUnread]);

  // Deep link from the "New customer message" email: /admin?order=<id>
  useEffect(() => {
    const orderId = new URLSearchParams(window.location.search).get("order");
    if (!orderId || deepLinked.current) return;
    deepLinked.current = true;
    setTab("orders");
    openChat(orderId, { toggle: false });
  }, [openChat]);

  useEffect(() => {
    if (tab === "settings") {
      loadStats();
      api
        .get("/settings/banner")
        .then(({ data }) => setBanner(data))
        .catch(() => {})
        .finally(() => setBannerLoaded(true));
    }
    if (tab === "waitlist") loadWaitlist();
  }, [tab, loadStats, loadWaitlist]);

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

  // Optimistic flag flip, rolled back if the API rejects it.
  const toggleFlag = async (product, field, request, messages) => {
    const next = !product[field];
    setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, [field]: next } : p)));
    try {
      await request(next);
      toast.success(next ? messages.on : messages.off);
    } catch (e) {
      setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, [field]: !next } : p)));
      toast.error(apiError(e));
    }
  };

  const toggleFeatured = (product) =>
    toggleFlag(
      product,
      "is_featured",
      (next) => api.patch(`/products/${product.id}/featured`, { is_featured: next }),
      {
        on: `${product.name} featured on the home page`,
        off: `${product.name} unfeatured`,
      }
    );

  const toggleComingSoon = (product) =>
    toggleFlag(product, "coming_soon", (next) => api.put(`/products/${product.id}`, { coming_soon: next }), {
      on: `${product.name} marked Coming Soon`,
      off: `${product.name} is on sale`,
    });

  const deleteProduct = async (product) => {
    if (!window.confirm(`Delete "${product.name}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/products/${product.id}`);
      toast.success(`${product.name} deleted`);
      loadProducts();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const runSync = async (apply) => {
    setSyncBusy(true);
    try {
      const { data } = apply
        ? await api.post("/admin/sync/catalog")
        : await api.get("/admin/sync/catalog");
      setSync(data);
      const pending = data.creates.length + data.updates.length;
      if (apply && data.errors.length) toast.error(`Pushed with ${data.errors.length} error(s)`);
      else if (apply) toast.success("Production catalog updated");
      else toast.success(pending ? `${pending} change(s) ready to push` : "Production already matches preview");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSyncBusy(false);
    }
  };

  const productName = (id) => products.find((p) => p.id === id)?.name || "General";

  return (
    <div data-testid="admin-page" className="mx-auto max-w-[1400px] px-5 py-14 lg:px-10 lg:py-20">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// operator console</p>
      <h1 className="mt-4 font-display text-3xl tracking-tighter">Admin</h1>

      <div className="mt-10 flex flex-wrap gap-3">
        {TABS.map((t) => (
          <button
            key={t.key}
            data-testid={`admin-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`relative border px-5 py-2 text-[10px] uppercase tracking-[0.25em] transition-colors ${
              tab === t.key ? "border-[#00ffcc] text-[#00ffcc]" : "border-zinc-800 text-zinc-500 hover:text-white"
            }`}
          >
            {t.label}
            {t.key === "orders" && unread.orders > 0 && (
              <span
                data-testid="orders-tab-unread-dot"
                title={`${unread.messages} unread customer message(s)`}
                className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 animate-pulse rounded-full bg-[#39ff14] shadow-[0_0_8px_2px_rgba(57,255,20,0.7)]"
              />
            )}
          </button>
        ))}
      </div>

      {tab === "orders" && (
        <OrdersTab
          orders={orders}
          creds={creds}
          openOrder={openOrder}
          onOpenChat={openChat}
          onSetStatus={setStatus}
          onReveal={reveal}
        />
      )}

      {tab === "products" && (
        <ProductsTab
          products={products}
          categories={categories}
          labelOf={labelOf}
          editingProduct={editingProduct}
          setEditingProduct={setEditingProduct}
          onSaved={() => {
            setEditingProduct(null);
            loadProducts();
          }}
          onDelete={deleteProduct}
          onToggleFeatured={toggleFeatured}
          onToggleComingSoon={toggleComingSoon}
          sync={sync}
          syncBusy={syncBusy}
          onCheckSync={() => runSync(false)}
          onPushSync={() => runSync(true)}
        />
      )}

      {tab === "categories" && <CategoriesTab categories={categories} reload={reloadCategories} />}

      {tab === "reviews" && <ReviewsTab />}

      {tab === "coupons" && <CouponsTab categories={categories} />}

      {tab === "waitlist" && <WaitlistTab waitlist={waitlist} productName={productName} />}

      {tab === "settings" && (
        <SettingsTab banner={banner} setBanner={setBanner} bannerLoaded={bannerLoaded}
                     stats={stats} reloadStats={loadStats} />
      )}
    </div>
  );
}
