import { Link, useNavigate } from "react-router-dom";
import { ShoppingCart, Menu, X } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useCart } from "@/context/CartContext";
import { NotificationBell } from "@/components/NotificationBell";

const linkCls =
  "text-xs uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:text-[#00ffcc]";

export const Navbar = () => {
  const { user, logout } = useAuth();
  const { count, setOpen } = useCart();
  const [mobile, setMobile] = useState(false);
  const navigate = useNavigate();

  const doLogout = async () => {
    await logout();
    setMobile(false);
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-50 border-b border-[#1f1f1f] bg-[#050505]/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between px-5 py-4 lg:px-10">
        <Link to="/" data-testid="brand-logo" className="font-display text-lg font-black tracking-tighter">
          POKE<span className="text-[#00ffcc] neon-text">COINS</span>
        </Link>

        <nav className="hidden items-center gap-10 md:flex">
          <Link to="/" className={linkCls} data-testid="nav-store">Store</Link>
          <Link to="/products" className={linkCls} data-testid="nav-products">Products</Link>
          <Link to="/about" className={linkCls} data-testid="nav-about">About Us</Link>
          <Link to="/reviews" className={linkCls} data-testid="nav-reviews">Reviews</Link>
          <Link to="/my-orders" className={linkCls} data-testid="nav-my-orders">My Orders</Link>
          <button onClick={() => setOpen(true)} className={linkCls} data-testid="nav-cart">
            Cart
          </button>
          {user?.role === "admin" && (
            <Link to="/admin" className={linkCls} data-testid="nav-admin">Admin</Link>
          )}
        </nav>

        <div className="flex items-center gap-3">
          <NotificationBell />
          <button
            data-testid="open-cart-btn"
            onClick={() => setOpen(true)}
            className="relative border border-zinc-800 p-2 text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
          >
            <ShoppingCart className="h-4 w-4" />
            {count > 0 && (
              <span
                data-testid="cart-count"
                className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center bg-[#00ffcc] px-1 text-[10px] font-bold text-black"
              >
                {count}
              </span>
            )}
          </button>
          {user ? (
            <button
              data-testid="logout-btn"
              onClick={doLogout}
              className="hidden border border-zinc-800 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:border-[#ff3b30] hover:text-[#ff3b30] md:block"
            >
              Log out
            </button>
          ) : (
            <Link
              to="/login"
              data-testid="login-link"
              className="hidden border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black md:block"
            >
              Sign in
            </Link>
          )}
          <button
            data-testid="mobile-menu-btn"
            className="border border-zinc-800 p-2 text-zinc-300 md:hidden"
            onClick={() => setMobile((v) => !v)}
          >
            {mobile ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {mobile && (
        <div data-testid="mobile-menu" className="flex flex-col gap-4 border-t border-[#1f1f1f] px-5 py-5 md:hidden">
          <Link to="/" className={linkCls} onClick={() => setMobile(false)}>Store</Link>
          <Link to="/products" className={linkCls} data-testid="mobile-nav-products" onClick={() => setMobile(false)}>
            Products
          </Link>
          <Link to="/about" className={linkCls} data-testid="mobile-nav-about" onClick={() => setMobile(false)}>
            About Us
          </Link>
          <Link to="/reviews" className={linkCls} data-testid="mobile-nav-reviews" onClick={() => setMobile(false)}>
            Reviews
          </Link>
          <Link
            to="/my-orders"
            className={linkCls}
            data-testid="mobile-nav-my-orders"
            onClick={() => setMobile(false)}
          >
            My Orders
          </Link>
          <button
            className={`${linkCls} text-left`}
            data-testid="mobile-nav-cart"
            onClick={() => {
              setMobile(false);
              setOpen(true);
            }}
          >
            Cart
          </button>
          {user?.role === "admin" && (
            <Link to="/admin" className={linkCls} onClick={() => setMobile(false)}>Admin</Link>
          )}
          {user ? (
            <button onClick={doLogout} className={`${linkCls} text-left`}>Log out</button>
          ) : (
            <Link to="/login" className={linkCls} onClick={() => setMobile(false)}>Sign in</Link>
          )}
        </div>
      )}
    </header>
  );
};
