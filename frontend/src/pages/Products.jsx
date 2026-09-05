import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useCategories } from "@/lib/useCategories";
import { ProductCard } from "@/components/ProductCard";
import { ReviewCarousel } from "@/components/ReviewCarousel";

export default function Products() {
  const [products, setProducts] = useState([]);
  const [tab, setTab] = useState("all");
  const { categories, labelOf } = useCategories();
  const order = useMemo(() => categories.map((c) => c.key), [categories]);
  const tabs = useMemo(
    () => [{ key: "all", label: "All" }, ...categories.map((c) => ({ key: c.key, label: c.label }))],
    [categories]
  );

  useEffect(() => {
    api.get("/products").then(({ data }) => setProducts(data)).catch(() => {});
  }, []);

  const visible = useMemo(() => {
    const list = tab === "all" ? products : products.filter((p) => p.category === tab);
    // Categories lead in the order set in the admin panel.
    return [...list].sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category));
  }, [products, tab, order]);

  return (
    <div data-testid="products-page" className="mx-auto max-w-[1400px] px-5 py-16 lg:px-10 lg:py-24">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// live inventory</p>
      <h1 className="mt-4 font-display text-4xl tracking-tighter sm:text-5xl">Products</h1>
      <p className="mt-5 max-w-xl text-sm leading-relaxed text-zinc-400">
        Wholesale Pokécoin drops, weekly event tickets, Platinum Medal services and elite Shundo hunting.
        Restocked every week as new events drop.
      </p>

      <div className="mt-12 flex flex-wrap gap-3 border-b border-[#1f1f1f] pb-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            data-testid={`filter-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`border px-4 py-2 text-[10px] uppercase tracking-[0.2em] transition-colors ${
              tab === t.key
                ? "border-[#00ffcc] text-[#00ffcc]"
                : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <motion.div
        key={tab}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.35 }}
        className="mt-12 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3 lg:gap-10"
      >
        {visible.map((p) => (
          <ProductCard key={p.id} product={p} />
        ))}
      </motion.div>

      {visible.length === 0 && (
        <p data-testid="products-empty" className="mt-12 text-xs text-zinc-600">
          Nothing listed in {tab === "all" ? "this category" : labelOf(tab)} right now — check back this week.
        </p>
      )}

      <ReviewCarousel />
    </div>
  );
}
