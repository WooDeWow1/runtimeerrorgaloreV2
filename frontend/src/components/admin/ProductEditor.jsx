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
        image_file: (p.image_url || "").replace("/images/", ""),
        sellauth_product_id: p.sellauth_product_id ?? "",
        active: p.active !== false,
        coming_soon: !!p.coming_soon,
        is_featured: !!p.is_featured,
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
      setForm((f) => ({ ...f, price: data.price, name: f.name || data.name }));
      toast.success(`SellAuth: ${data.name} — $${data.price} (variant ${data.sellauth_variant_id})`);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

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
      image_url: form.image_file ? `/images/${form.image_file.replace(/^\/?images\//, "")}` : "",
      sellauth_product_id: form.sellauth_product_id === "" ? null : Number(form.sellauth_product_id),
      active: form.active,
      coming_soon: form.coming_soon,
      is_featured: form.is_featured,
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

  const preview = form.image_file ? `/images/${form.image_file.replace(/^\/?images\//, "")}` : "";

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
            className={`${input} h-24`}
            value={form.description}
            onChange={set("description")}
          />
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
          <label className={label}>Image filename</label>
          <input
            data-testid="product-image-input"
            className={input}
            value={form.image_file}
            onChange={set("image_file")}
            placeholder="stardust.jpg"
          />
          <p className="mt-1.5 text-[10px] text-zinc-600">Looked up in frontend/public/images.</p>
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
