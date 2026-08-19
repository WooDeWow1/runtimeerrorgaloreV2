import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import { CartProvider } from "@/context/CartContext";
import { Navbar } from "@/components/Navbar";
import { CartDrawer } from "@/components/CartDrawer";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { useVisitTracker } from "@/hooks/useVisitTracker";
import Home from "@/pages/Home";
import Products from "@/pages/Products";
import About from "@/pages/About";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Checkout from "@/pages/Checkout";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import Dashboard from "@/pages/Dashboard";
import OrderDetail from "@/pages/OrderDetail";
import Admin from "@/pages/Admin";

function App() {
  useVisitTracker();
  return (
    <div className="App min-h-screen bg-[#050505] text-white">
      <BrowserRouter>
        <AuthProvider>
          <CartProvider>
            <Navbar />
            <CartDrawer />
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/products" element={<Products />} />
              <Route path="/about" element={<About />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/checkout" element={<Checkout />} />
              <Route path="/payment/success" element={<PaymentSuccess />} />
              <Route path="/payment/cancel" element={<PaymentCancel />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/orders/:id" element={<OrderDetail />} />
              <Route path="/order/:id" element={<OrderDetail />} />
              <Route
                path="/admin"
                element={
                  <ProtectedRoute adminOnly>
                    <Admin />
                  </ProtectedRoute>
                }
              />
            </Routes>
            <Toaster
              theme="dark"
              position="top-right"
              toastOptions={{
                style: {
                  background: "#0a0a0a",
                  border: "1px solid #00ffcc55",
                  borderRadius: 0,
                  color: "#fff",
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: "12px",
                },
              }}
            />
          </CartProvider>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
