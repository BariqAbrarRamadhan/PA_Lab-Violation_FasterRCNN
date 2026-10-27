"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Video, Wifi, WifiOff } from "lucide-react";

interface NavbarProps {
  isConnected: boolean;
}

export default function Navbar({ isConnected }: NavbarProps) {
  const pathname = usePathname();

  const navLinks = [
    { href: "/", label: "Upload Video" },
    { href: "/url", label: "Stream URL" },
    { href: "/history", label: "Riwayat" },
  ];

  return (
    <header
      className="sticky top-0 z-50 text-white flex items-center justify-between px-4 md:px-8"
      style={{ background: "#0f172a", height: 60, boxShadow: "0 2px 12px rgba(0,0,0,.3)" }}
    >
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 bg-sky-500 rounded-lg flex items-center justify-center">
          <Video size={18} className="text-white" />
        </div>
        <span className="font-bold text-base tracking-tight">SafeVision Lab</span>
      </div>

      <nav className="flex gap-1">
        {navLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors flex items-center gap-1.5 ${
              pathname === link.href
                ? "bg-sky-500 text-white"
                : "text-slate-400 hover:text-white hover:bg-white/10"
            }`}
          >
            <span className="hidden sm:inline">{link.label}</span>
          </Link>
        ))}
      </nav>

      <div className="hidden md:flex items-center gap-3">
        <span className="text-xs font-semibold px-3 py-1 rounded-full bg-sky-500/15 text-sky-400 border border-sky-500/30">
          Faster R-CNN
        </span>
        <div className="flex items-center gap-1.5 text-xs">
          {isConnected ? (
            <>
              <Wifi size={12} className="text-emerald-400" />
              <span className="text-emerald-400">On</span>
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-red-400" />
              <span className="text-red-400">Off</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
