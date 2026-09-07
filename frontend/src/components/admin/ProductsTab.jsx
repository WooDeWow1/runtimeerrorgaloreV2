import { Image as ImageIcon, Pencil, Plus, Star, Trash2, UploadCloud } from "lucide-react";
import { money } from "@/lib/api";
import { ProductEditor } from "@/components/admin/ProductEditor";

const CatalogSyncPanel = ({ sync, syncBusy, onCheck, onPush, labelOf }) => (
  <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-5" data-testid="catalog-sync-panel">
    <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
      <UploadCloud className="h-4 w-4 text-[#00ffcc]" /> Push catalog live
    </h2>
    <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
      Copies this catalog — names, images, SellAuth ids, featured stars and Coming Soon flags — to the
      live site. Check first, then push. Nothing is ever deleted from production.
    </p>
    <div className="mt-4 flex flex-wrap gap-3">
      <button
        data-testid="sync-check-btn"
        disabled={syncBusy}
        onClick={onCheck}
        className="border border-zinc-800 px-5 py-2 text-[10px] uppercase tracking-[0.25em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc] disabled:opacity-40"
      >
        {syncBusy ? "Working…" : "Check differences"}
      </button>
      <button
        data-testid="sync-push-btn"
        disabled={syncBusy || !sync || sync.creates.length + sync.updates.length === 0}
        onClick={onPush}
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
            <span className="text-[#00ffcc]">NEW</span> {c.name} · {labelOf(c.category)} · {money(c.price)}
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
);

const ProductRow = ({ product: p, labelOf, onEdit, onDelete, onToggleFeatured, onToggleComingSoon }) => (
  <div
    data-testid={`admin-product-${p.id}`}
    className="flex flex-wrap items-center gap-4 border border-[#1f1f1f] bg-[#0a0a0a] p-4"
  >
    {p.image_url && <img src={p.image_url} alt={p.name} className="h-14 w-14 object-cover" />}
    <div className="min-w-[200px] flex-1">
      <p className="text-xs font-bold">{p.name}</p>
      <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
        {labelOf(p.category)} · {money(p.price)}
        {p.sellauth_product_id ? ` · SA ${p.sellauth_product_id}` : " · not in SellAuth"}
        {p.variants?.length > 0 ? ` · ${p.variants.length} options` : ""}
        {p.coming_soon ? " · soon" : ""}
        {p.is_featured ? " · featured" : ""}
        {p.active === false ? " · hidden" : ""}
      </p>
    </div>
    <button
      data-testid={`edit-product-${p.id}`}
      onClick={() => onEdit(p)}
      className="border border-zinc-800 p-2 text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
    >
      <Pencil className="h-3.5 w-3.5" />
    </button>
    <button
      data-testid={`delete-product-${p.id}`}
      onClick={() => onDelete(p)}
      className="border border-zinc-800 p-2 text-zinc-400 transition-colors hover:border-[#ff3b30] hover:text-[#ff3b30]"
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
    <button
      data-testid={`toggle-featured-${p.id}`}
      aria-pressed={p.is_featured}
      title={p.is_featured ? "Remove from home page" : "Feature on home page"}
      onClick={() => onToggleFeatured(p)}
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
      onClick={() => onToggleComingSoon(p)}
      className={`border px-4 py-2 text-[10px] uppercase tracking-[0.2em] transition-colors ${
        p.coming_soon
          ? "border-[#9966cc] text-[#c7a6f0]"
          : "border-zinc-800 text-zinc-500 hover:border-[#9966cc] hover:text-[#c7a6f0]"
      }`}
    >
      {p.coming_soon ? "Coming soon" : "On sale"}
    </button>
  </div>
);

export const ProductsTab = ({
  products,
  categories,
  labelOf,
  editingProduct,
  setEditingProduct,
  onSaved,
  onDelete,
  onToggleFeatured,
  onToggleComingSoon,
  sync,
  syncBusy,
  onCheckSync,
  onPushSync,
  onSyncImages,
}) => (
  <div className="mt-10" data-testid="admin-products-list">
    <CatalogSyncPanel
      sync={sync}
      syncBusy={syncBusy}
      onCheck={onCheckSync}
      onPush={onPushSync}
      labelOf={labelOf}
    />

    <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
      <p className="max-w-2xl text-[10px] leading-relaxed text-zinc-600">
        Add or edit products here — the SellAuth variant ID, live price and product image are pulled
        from your SellAuth dashboard automatically. Only the two Coming Soon Shundo products use a
        local image file.
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          data-testid="sync-images-btn"
          onClick={onSyncImages}
          className="flex items-center gap-2 border border-zinc-800 px-4 py-2 text-[10px] uppercase tracking-[0.25em] text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
        >
          <ImageIcon className="h-3 w-3" /> Refresh images
        </button>
        <button
          data-testid="new-product-btn"
          onClick={() => setEditingProduct("new")}
          className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
        >
          <Plus className="h-3 w-3" /> Add product
        </button>
      </div>
    </div>

    {editingProduct && (
      <div className="mt-6">
        <ProductEditor
          product={editingProduct === "new" ? null : editingProduct}
          categories={categories}
          onCancel={() => setEditingProduct(null)}
          onSaved={onSaved}
        />
      </div>
    )}

    <div className="mt-8 space-y-4">
      {products.map((p) => (
        <ProductRow
          key={p.id}
          product={p}
          labelOf={labelOf}
          onEdit={setEditingProduct}
          onDelete={onDelete}
          onToggleFeatured={onToggleFeatured}
          onToggleComingSoon={onToggleComingSoon}
        />
      ))}
    </div>
  </div>
);
