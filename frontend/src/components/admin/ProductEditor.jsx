import { useState } from "react";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";

const blank = {
  name: "",
  description: "",
  category: "",
  price: "",
  msrp: "",
  badge: "",
  image_file: "",
  sellauth_product_id: "",
  active: true,
  coming_soon: false,
  is_featured: false,
  variants: [],
};

const toForm = (p) =>
  !p
    ? blank
    : {
        name: p.name || "",
        description: p.description || "",
        category: p.category || "",
        price: p.price ?? "",
        msrp: p.msrp ?? "",
        badge: p.badge || "",
        image_file: (p.image_url || "").startsWith("http")
          ? ""
          : (p.image_url || "").replace("/images/", ""),
        sellauth_product_id: p.sellauth_product_id ?? "",
        active: p.active !== false,
        coming_soon: !!p.coming_soon,
        is_featured: !!p.is_featured,
        variants: (p.variants || []).map((v) => ({
          uid: `${v.sellauth_variant_id}`,
          label: v.label,
          sellauth_variant_id: v.sellauth_variant_id,
          price: v.price,
        })),
      };

export const ProductEditor = ({ product, categories, onSaved, onCancel }) => {
  const [form, setForm] = useState(toForm(product));
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const fetchFromSellAuth = async () => {
    if (!form.sellauth_product_id) return toast.error("Enter a SellAuth product ID first");
    try {
      const { data } = await api.get(`/admin/sellauth/products/${form.sellauth_product_id}`);
      setForm((f) => ({
        ...f,
        price: data.price,
        name: f.name || data.name,
        variants:
          data.variants.length > 1 && f.variants.length === 0 ? data.variants : f.variants,
      }));
      toast.success(
        `SellAuth: ${data.name} — $${data.price} · ${data.variants.length} variant(s) found`
      );
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const setVariant = (n, key) => (e) =>
    setForm((f) => ({
      ...f,
      variants: f.variants.map((v, idx) => (idx === n ? { ...v, [key]: e.target.value } : v)),
    }));

  const addVariant = () =>
    setForm((f) => ({
      ...f,
      variants: [
        ...f.variants,
        { uid: crypto.randomUUID(), label: "", sellauth_variant_id: "", price: "" },
      ],
    }));

  const removeVariant = (n) =>
    setForm((f) => ({ ...f, variants: f.variants.filter((_, idx) => idx !== n) }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      description: form.description,
      category: form.category,
      price: Number(form.price),
      msrp: form.msrp === "" ? null : Number(form.msrp),
      badge: form.badge,
      // Blank means "use the SellAuth image": sending "" would wipe the synced URL.
      ...(form.image_file || !form.sellauth_product_id
        ? {
            image_url: form.image_file
              ? `/images/${form.image_file.replace(/^\/?images\//, "")}`
              : "",
          }
        : {}),
      sellauth_product_id: form.sellauth_product_id === "" ? null : Number(form.sellauth_product_id),
      active: form.active,
      coming_soon: form.coming_soon,
      is_featured: form.is_featured,
      variants: form.variants
        .filter((v) => v.label && v.sellauth_variant_id && v.price)
        .map((v) => ({
          label: v.label.trim(),
          sellauth_variant_id: Number(v.sellauth_variant_id),
          price: Number(v.price),
        })),
    };
    try {
      if (product) await api.put(`/products/${product.id}`, payload);
      else await api.post("/products", payload);
      toast.success(product ? "Product updated" : "Product created");
      onSaved();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const localImage = form.image_file
    ? `/images/${form.image_file.replace(/^\/?images\//, "")}`
    : "";
  const remoteImage = (product?.image_url || "").startsWith("http") ? product.image_url : "";
  const preview = localImage || remoteImage;

  return (
    <form
      onSubmit={submit}
      data-testid="product-form"
      className="border border-[#00ffcc]/30 bg-[#0a0a0a] p-5"
    >
      <h3 className="font-display text-sm uppercase tracking-[0.2em] text-[#00ffcc]">
        {product ? `Edit — ${product.name}` : "Add product"}
      </h3>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <div>
          <label className={label}>Name</label>
          <input data-testid="product-name-input" className={input} value={form.name} onChange={set("name")} required />
        </div>
        <div>
          <label className={label}>Category</label>
          <select
            data-testid="product-category-select"
            className={input}
            value={form.category}
            onChange={set("category")}
            required
          >
            <option value="">Select…</option>
            {categories.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Description</label>
          <textarea
            data-testid="product-description-input"
            className={`${input} h-40 font-mono leading-relaxed`}
            value={form.description}
            onChange={set("description")}
          />
          <p className="mt-1.5 text-[10px] text-zinc-600">
            Line breaks and blank lines are kept exactly as typed on the storefront.
          </p>
        </div>
        <div>
          <label className={label}>SellAuth Product ID</label>
          <div className="flex gap-2">
            <input
              data-testid="product-sellauth-id-input"
              className={input}
              value={form.sellauth_product_id}
              onChange={set("sellauth_product_id")}
              placeholder="e.g. 857694"
            />
            <button
              type="button"
              data-testid="fetch-sellauth-btn"
              onClick={fetchFromSellAuth}
              className="shrink-0 border border-[#00ffcc] px-3 text-[10px] uppercase tracking-[0.2em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black"
            >
              Fetch
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-zinc-600">
            The variant ID and live price are pulled from SellAuth automatically on save.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={label}>Price ($)</label>
            <input
              data-testid="product-price-input"
              className={input}
              type="number"
              step="0.01"
              value={form.price}
              onChange={set("price")}
              required
            />
          </div>
          <div>
            <label className={label}>MSRP ($)</label>
            <input
              data-testid="product-msrp-input"
              className={input}
              type="number"
              step="0.01"
              value={form.msrp}
              onChange={set("msrp")}
            />
          </div>
        </div>
        <div>
          <label className={label}>Image filename (optional)</label>
          <input
            data-testid="product-image-input"
            className={input}
            value={form.image_file}
            onChange={set("image_file")}
            placeholder={remoteImage ? "Using the SellAuth image" : "stardust.jpg"}
          />
          <p className="mt-1.5 text-[10px] text-zinc-600">
            {remoteImage
              ? "Pulled from SellAuth automatically. Only fill this in to override it."
              : "Leave blank when a SellAuth product ID is set — the shop image is used."}
          </p>
        </div>
        <div>
          <label className={label}>Badge</label>
          <input data-testid="product-badge-input" className={input} value={form.badge} onChange={set("badge")} />
        </div>
        <div className="sm:col-span-2 flex flex-wrap items-center gap-6">
          {[
            ["active", "Visible on site"],
            ["coming_soon", "Coming soon"],
            ["is_featured", "Featured on home"],
          ].map(([key, text]) => (
            <label key={key} className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-400">
              <input
                data-testid={`product-${key}-toggle`}
                type="checkbox"
                checked={form[key]}
                onChange={set(key)}
              />
              {text}
            </label>
          ))}
          {preview && (
            <img
              data-testid="product-image-preview"
              src={preview}
              alt="preview"
              className="h-14 w-14 border border-zinc-800 object-cover"
            />
          )}
        </div>
      </div>

      <div className="mt-6 border-t border-zinc-900 pt-5" data-testid="variants-editor">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-400">Variants / options</p>
            <p className="mt-1 text-[10px] text-zinc-600">
              Leave empty for a single-price product. With options, the card shows a dropdown and the
              chosen SellAuth variant ID is what gets bought.
            </p>
          </div>
          <button
            type="button"
            data-testid="add-variant-btn"
            onClick={addVariant}
            className="border border-zinc-700 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 hover:border-[#00ffcc] hover:text-[#00ffcc]"
          >
            + Add option
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {form.variants.map((v, n) => (
            <div key={v.uid} data-testid={`variant-row-${n}`} className="grid gap-3 sm:grid-cols-[1fr_140px_120px_auto]">
              <input
                data-testid={`variant-label-input-${n}`}
                className={input}
                placeholder="Label (e.g. Ultra Box)"
                value={v.label}
                onChange={setVariant(n, "label")}
              />
              <input
                data-testid={`variant-id-input-${n}`}
                className={input}
                placeholder="Variant ID"
                value={v.sellauth_variant_id}
                onChange={setVariant(n, "sellauth_variant_id")}
              />
              <input
                data-testid={`variant-price-input-${n}`}
                className={input}
                type="number"
                step="0.01"
                placeholder="Price"
                value={v.price}
                onChange={setVariant(n, "price")}
              />
              <button
                type="button"
                data-testid={`remove-variant-${n}`}
                onClick={() => removeVariant(n)}
                className="border border-zinc-800 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-500 hover:border-[#ff3b30] hover:text-[#ff3b30]"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 flex gap-3">
        <button
          data-testid="save-product-btn"
          disabled={busy}
          className="border border-[#00ffcc] px-6 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
        >
          {busy ? "Saving…" : product ? "Save changes" : "Create product"}
        </button>
        <button
          type="button"
          data-testid="cancel-product-btn"
          onClick={onCancel}
          className="border border-zinc-800 px-6 py-2 text-[10px] uppercase tracking-[0.25em] text-zinc-400 hover:text-white"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};
