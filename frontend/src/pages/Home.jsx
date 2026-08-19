import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ShieldCheck, Zap, Lock } from "lucide-react";
import { api, CATEGORY_LABELS } from "@/lib/api";
import { ProductCard } from "@/components/ProductCard";
import { useCart } from "@/context/CartContext";

const HERO = "/images/snorlax.jpg";
const GENGAR = "/images/Mainpage.jpg";
const PSYDUCK = "/images/psyduck.jpg";

const SECTIONS = [
  { key: "pokecoin_bundle", note: "Required for passes", noteClass: "text-zinc-600" },
  { key: "event_pass", note: "Bundle required", noteClass: "text-[#f4d03f]" },
  { key: "medals", note: "Standalone or bundled", noteClass: "text-[#c7a6f0]" },
  { key: "stardust", note: "Farmed by operators", noteClass: "text-zinc-600" },
  { key: "shundo_service", note: "Operator fleet", noteClass: "text-[#c7a6f0]" },
];

export default function Home() {
  const [products, setProducts] = useState([]);
  const { setOpen } = useCart();

  useEffect(() => {
    api.get("/products").then(({ data }) => setProducts(data)).catch(() => {});
  }, []);

  const featured = products.filter((p) => p.is_featured);
  const byCat = (c) => featured.filter((p) => p.category === c);
  const hasAnyFeatured = featured.length > 0;

  return (
    <div data-testid="home-page">
      {/* HERO */}
      <section className="scanlines relative overflow-hidden border-b border-[#1f1f1f]">
        <img src={HERO} alt="Snorlax" className="absolute inset-0 h-full w-full object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#050505] via-[#050505]/85 to-transparent" />
        <div className="relative mx-auto grid max-w-[1400px] gap-10 px-5 py-24 lg:grid-cols-12 lg:px-10 lg:py-36">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7 }}
            className="lg:col-span-7"
          >
            <p className="mb-6 text-xs font-bold uppercase tracking-[0.35em] text-[#00ffcc]">
              // underground trainer supply
            </p>
            <h1 className="font-display text-4xl font-black leading-none tracking-tighter sm:text-5xl lg:text-6xl">
              POKÉCOINS.<br />
              EVENT PASSES.<br />
              <span className="text-[#00ffcc] neon-text">DELIVERED.</span>
            </h1>
            <p className="mt-8 max-w-lg text-base leading-relaxed text-zinc-400">
              Unlimited raids. Bottomless coins. Fraction of the price. Bypass expensive in-game stores with
              the cheapest PokéCoin drops and weekly ticket deals in the scene. Keep your inventory locked and
              loaded 24/7.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <a
                href="#store"
                data-testid="hero-shop-btn"
                className="border border-[#00ffcc] px-8 py-4 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
              >
                Browse Stock
              </a>
              <button
                onClick={() => setOpen(true)}
                data-testid="hero-cart-btn"
                className="border border-zinc-700 px-8 py-4 text-[11px] uppercase tracking-[0.3em] text-zinc-300 transition-colors hover:border-white hover:text-white"
              >
                View Cart
              </button>
            </div>
          </motion.div>

          <div className="hidden lg:col-span-5 lg:flex lg:items-end lg:justify-end">
            <motion.img
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.9, delay: 0.2 }}
              src={GENGAR}
              alt="PokeCoins hero artwork"
              className="w-full max-w-[520px] border border-[#00ffcc]/30 object-cover"
            />
          </div>
        </div>
      </section>

      {/* TRUST STRIP */}
      <section className="border-b border-[#1f1f1f] bg-[#080808]">
        <div className="mx-auto grid max-w-[1400px] gap-8 px-5 py-12 sm:grid-cols-3 lg:px-10">
          {[
            { icon: Lock, title: "AES Encrypted PTC", body: "Credentials sealed with Fernet symmetric encryption. Never stored as plain text." },
            { icon: Zap, title: "Fast Fulfilment", body: "Most Pokécoin bundles are processed within the hour of payment clearing." },
            { icon: ShieldCheck, title: "Stay-Logged-Out Alerts", body: "You get pinged the second an operator logs in and again when it's done." },
          ].map((f) => (
            <div key={f.title} className="border border-[#141414] p-6">
              <f.icon className="h-5 w-5 text-[#00ffcc]" />
              <h3 className="mt-4 font-display text-sm uppercase tracking-wide">{f.title}</h3>
              <p className="mt-2 text-xs leading-relaxed text-zinc-500">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURED STORE — only starred products, empty categories hidden */}
      <section id="store" className="mx-auto max-w-[1400px] px-5 py-20 lg:px-10 lg:py-28">
        {SECTIONS.map(({ key, note, noteClass }) => {
          const items = byCat(key);
          if (items.length === 0) return null;
          return (
            <div key={key} data-testid={`home-section-${key}`} className="mb-24 last:mb-0">
              <div className="mb-12 flex items-end justify-between gap-6 border-b border-[#1f1f1f] pb-6">
                <h2 className="font-display text-2xl tracking-tight sm:text-3xl lg:text-4xl">
                  {CATEGORY_LABELS[key]}
                </h2>
                <span className={`text-[10px] uppercase tracking-[0.25em] ${noteClass}`}>{note}</span>
              </div>
              <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3 lg:gap-10">
                {items.map((p) => (
                  <ProductCard key={p.id} product={p} featured={key === "event_pass"} />
                ))}
              </div>
            </div>
          );
        })}

        {!hasAnyFeatured && (
          <p data-testid="home-no-featured" className="text-xs text-zinc-600">
            No featured products right now — browse the full catalog for everything in stock.
          </p>
        )}

        <div className="mt-16 flex justify-center">
          <Link
            to="/products"
            data-testid="home-all-products-btn"
            className="border border-zinc-700 px-8 py-4 text-[11px] uppercase tracking-[0.3em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
          >
            View full catalog
          </Link>
        </div>
      </section>

      {/* SHUNDO — COMING SOON */}
      <section className="relative overflow-hidden border-y border-[#1f1f1f] bg-[#070707] py-20 lg:py-28">
        <div className="pointer-events-none absolute inset-0 flex items-center opacity-[0.06]">
          <div className="marquee-track flex whitespace-nowrap">
            {[0, 1].map((k) => (
              <span key={k} className="font-display text-7xl font-black tracking-tighter lg:text-9xl">
                SHUNDO HUNTING · ITOOLS · PGTOOLS · REGIBOT · SHUNGO&nbsp;
              </span>
            ))}
          </div>
        </div>
        <div className="relative mx-auto grid max-w-[1400px] gap-12 px-5 lg:grid-cols-12 lg:px-10">
          <div className="lg:col-span-6">
            <p className="text-xs font-bold uppercase tracking-[0.35em] text-[#9966cc]">// phase two</p>
            <h2 className="mt-5 font-display text-2xl tracking-tight sm:text-3xl lg:text-4xl">
              Phase Two — Hunting Fleet
            </h2>
            <p className="mt-6 max-w-lg text-sm leading-relaxed text-zinc-400">
              Advanced, targeted Shundo acquisition handled by our dedicated operator fleet. We use a private
              suite of secure simulation tools to hunt down your exact shiny-hundos while keeping your account
              completely safe. Onboarding opens soon
            </p>
            <span className="mt-8 inline-block border border-[#9966cc] px-5 py-3 text-[10px] uppercase tracking-[0.3em] text-[#9966cc]">
              Coming Soon
            </span>
          </div>
          <div className="grid gap-8 sm:grid-cols-2 lg:col-span-6">
            <img src={PSYDUCK} alt="Psyduck" className="border border-[#1f1f1f] object-cover sm:col-span-2" />
          </div>
        </div>
      </section>

      <footer className="mx-auto max-w-[1400px] px-5 py-12 text-[10px] uppercase tracking-[0.25em] text-zinc-600 lg:px-10">
        © 2026 PokeCoins.cc · unofficial fan marketplace · not affiliated with Niantic or The Pokémon Company
      </footer>
    </div>
  );
}
