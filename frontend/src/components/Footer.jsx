import { Link } from "react-router-dom";

const DISCLAIMER =
  "PokeCoins.cc is not affiliated with, endorsed by, or sponsored by Niantic, Inc., The Pokémon Company, or Nintendo. All trademarks are the property of their respective owners.";

const links = [
  { to: "/legal?doc=privacy", label: "Privacy Policy", testid: "footer-privacy-link" },
  { to: "/legal?doc=terms", label: "Terms of Service", testid: "footer-terms-link" },
  { to: "/legal?doc=terms#refunds", label: "Refund Policy", testid: "footer-refund-link" },
];

export const Footer = () => (
  <footer
    data-testid="site-footer"
    className="mt-24 border-t border-[#1f1f1f] bg-[#050505] px-5 py-12 lg:px-10"
  >
    <div className="mx-auto max-w-[1400px]">
      <div className="flex flex-wrap items-center justify-between gap-6">
        <p className="font-display text-sm tracking-tight text-white">
          POKE<span className="text-[#00ffcc]">COINS</span>
        </p>
        <nav className="flex flex-wrap gap-x-7 gap-y-3">
          {links.map((l) => (
            <Link
              key={l.testid}
              to={l.to}
              data-testid={l.testid}
              className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 transition-colors hover:text-[#00ffcc]"
            >
              {l.label}
            </Link>
          ))}
          <a
            href="mailto:support@pokecoins.cc"
            data-testid="footer-support-link"
            className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 transition-colors hover:text-[#00ffcc]"
          >
            Support
          </a>
        </nav>
      </div>
      <p
        data-testid="footer-disclaimer"
        className="mt-8 max-w-3xl text-[10px] leading-relaxed text-zinc-600"
      >
        {DISCLAIMER}
      </p>
      <p className="mt-4 text-[10px] uppercase tracking-[0.2em] text-zinc-700">
        © {new Date().getFullYear()} PokeCoins.cc · 18+ only
      </p>
    </div>
  </footer>
);
