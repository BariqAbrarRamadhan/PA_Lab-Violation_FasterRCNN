"use client";

import { useEffect, useState } from "react";
import { BarChart3, TrendingUp, AlertTriangle, Eye, Calendar } from "lucide-react";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";

interface StatsData {
  total: number;
  by_type: Record<string, number>;
  data: Array<{
    object_name: string;
    confidence: number;
    timestamp: string;
    frame_time: string;
  }>;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch("http://localhost:5000/api/detections/stats");
      const data = await res.json();
      setStats(data);
    } catch (e) {
      console.error("Error fetching stats:", e);
    } finally {
      setIsLoading(false);
    }
  };

  // Helper: hitung deteksi per hari (7 hari terakhir)
  const getDailyData = () => {
    if (!stats?.data) return [];
    const today = new Date();
    const days: { label: string; count: number }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().split("T")[0];
      const label = d.toLocaleDateString("id-ID", { weekday: "short", day: "numeric" });
      const count = stats.data.filter((det) => det.timestamp?.startsWith(dateStr)).length;
      days.push({ label, count });
    }
    return days;
  };

  // Helper: hitung jam puncak
  const getHourlyData = () => {
    if (!stats?.data) return [];
    const hours: Record<number, number> = {};
    for (let h = 0; h < 24; h++) hours[h] = 0;
    stats.data.forEach((det) => {
      if (det.timestamp) {
        const hour = new Date(det.timestamp).getHours();
        hours[hour]++;
      }
    });
    return Object.entries(hours)
      .map(([h, count]) => ({ hour: parseInt(h), count }))
      .filter((_, i) => i >= 6 && i <= 22); // Hanya jam 6-22
  };

  // Helper: rata-rata confidence
  const getAvgConfidence = () => {
    if (!stats?.data?.length) return 0;
    const sum = stats.data.reduce((acc, d) => acc + (d.confidence || 0), 0);
    return (sum / stats.data.length) * 100;
  };

  // Helper: bar chart rendering
  const maxDailyCount = Math.max(...getDailyData().map((d) => d.count), 1);
  const maxHourlyCount = Math.max(...getHourlyData().map((d) => d.count), 1);

  const typeColors: Record<string, { bg: string; bar: string; emoji: string }> = {
    eating: { bg: "bg-amber-50", bar: "bg-amber-400", emoji: "🍕" },
    sleep: { bg: "bg-indigo-50", bar: "bg-indigo-400", emoji: "😴" },
    "playing game phone": { bg: "bg-rose-50", bar: "bg-rose-400", emoji: "📱" },
  };

  if (isLoading) {
    return (
      <div className="flex flex-col min-h-screen" style={{ background: "#f0f4f8" }}>
        <Navbar isConnected={false} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center animate-pulse">
            <BarChart3 size={48} className="mx-auto text-sky-400 mb-4" />
            <p className="text-slate-500 font-medium">Memuat dashboard...</p>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#f0f4f8" }}>
      <Navbar isConnected={false} />

      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-8 py-6 space-y-6">
        {/* Page Header */}
        <div className="anim-in">
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2.5">
            <BarChart3 size={24} className="text-sky-500" />
            Dashboard Statistik
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Ringkasan data deteksi pelanggaran keseluruhan.
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 anim-in-1">
          {/* Total Deteksi */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Deteksi</span>
              <div className="w-9 h-9 bg-sky-100 rounded-xl flex items-center justify-center">
                <Eye size={18} className="text-sky-500" />
              </div>
            </div>
            <p className="text-3xl font-bold text-slate-800">{stats?.total || 0}</p>
            <p className="text-xs text-slate-400 mt-1">Seluruh pelanggaran tercatat</p>
          </div>

          {/* Jenis Terbanyak */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Pelanggaran Terbanyak</span>
              <div className="w-9 h-9 bg-amber-100 rounded-xl flex items-center justify-center">
                <AlertTriangle size={18} className="text-amber-500" />
              </div>
            </div>
            {stats?.by_type && Object.keys(stats.by_type).length > 0 ? (
              <>
                <p className="text-3xl font-bold text-slate-800">
                  {Object.entries(stats.by_type).sort((a, b) => b[1] - a[1])[0]?.[1] || 0}
                </p>
                <p className="text-xs text-slate-400 mt-1 capitalize flex items-center gap-1">
                  {typeColors[Object.entries(stats.by_type).sort((a, b) => b[1] - a[1])[0]?.[0]]?.emoji}{" "}
                  {Object.entries(stats.by_type).sort((a, b) => b[1] - a[1])[0]?.[0]}
                </p>
              </>
            ) : (
              <p className="text-xl text-slate-400">—</p>
            )}
          </div>

          {/* Rata-rata Confidence */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Rata-rata Confidence</span>
              <div className="w-9 h-9 bg-emerald-100 rounded-xl flex items-center justify-center">
                <TrendingUp size={18} className="text-emerald-500" />
              </div>
            </div>
            <p className="text-3xl font-bold text-slate-800">{getAvgConfidence().toFixed(1)}%</p>
            <p className="text-xs text-slate-400 mt-1">Akurasi deteksi model</p>
          </div>

          {/* Jumlah Hari Aktif */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Hari Aktif</span>
              <div className="w-9 h-9 bg-violet-100 rounded-xl flex items-center justify-center">
                <Calendar size={18} className="text-violet-500" />
              </div>
            </div>
            <p className="text-3xl font-bold text-slate-800">
              {new Set(stats?.data?.map((d) => d.timestamp?.split("T")[0]).filter(Boolean)).size || 0}
            </p>
            <p className="text-xs text-slate-400 mt-1">Hari dengan deteksi aktif</p>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 anim-in-2">
          {/* Distribution by Type (Horizontal bars) */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200">
              <h2 className="text-sm font-semibold text-slate-800">Distribusi Jenis Pelanggaran</h2>
            </div>
            <div className="p-6 space-y-4">
              {stats?.by_type && Object.keys(stats.by_type).length > 0 ? (
                Object.entries(stats.by_type)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, count]) => {
                    const maxCount = Math.max(...Object.values(stats.by_type));
                    const pct = (count / maxCount) * 100;
                    const colors = typeColors[name] || { bg: "bg-slate-50", bar: "bg-slate-400", emoji: "❓" };
                    return (
                      <div key={name}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-sm font-medium text-slate-700 capitalize flex items-center gap-1.5">
                            {colors.emoji} {name}
                          </span>
                          <span className="text-sm font-bold text-slate-800">{count}</span>
                        </div>
                        <div className={`w-full h-3 rounded-full ${colors.bg}`}>
                          <div
                            className={`h-full rounded-full ${colors.bar} transition-all duration-700`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })
              ) : (
                <p className="text-sm text-slate-400 text-center py-8 italic">Belum ada data.</p>
              )}
            </div>
          </div>

          {/* Daily Trend (Vertical bars) */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200">
              <h2 className="text-sm font-semibold text-slate-800">Tren 7 Hari Terakhir</h2>
            </div>
            <div className="p-6">
              <div className="flex items-end gap-3 justify-between" style={{ height: 200 }}>
                {getDailyData().map((day, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-xs font-bold text-slate-700">{day.count}</span>
                    <div
                      className="w-full bg-sky-400 rounded-t-lg transition-all duration-700 hover:bg-sky-500"
                      style={{
                        height: `${Math.max((day.count / maxDailyCount) * 160, day.count > 0 ? 8 : 2)}px`,
                        minHeight: day.count > 0 ? "8px" : "2px",
                      }}
                    />
                    <span className="text-[10px] text-slate-400 font-medium mt-1">{day.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Hourly Distribution */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden anim-in-2">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-800">Distribusi Jam (06:00 - 22:00)</h2>
            <p className="text-xs text-slate-400 mt-0.5">Jam-jam puncak terjadinya pelanggaran</p>
          </div>
          <div className="p-6">
            <div className="flex items-end gap-1.5 justify-between" style={{ height: 160 }}>
              {getHourlyData().map((item, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5 group">
                  <span className="text-[9px] font-bold text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    {item.count}
                  </span>
                  <div
                    className="w-full bg-violet-300 rounded-t transition-all duration-500 hover:bg-violet-500"
                    style={{
                      height: `${Math.max((item.count / maxHourlyCount) * 120, item.count > 0 ? 6 : 2)}px`,
                    }}
                  />
                  <span className="text-[9px] text-slate-400 font-medium">{String(item.hour).padStart(2, "0")}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
