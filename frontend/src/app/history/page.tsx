"use client";

import { useEffect, useState } from "react";
import { Clock, Search, Download, ChevronLeft, ChevronRight, X, Filter } from "lucide-react";
import * as XLSX from "xlsx";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";

interface Detection {
  id: number;
  frame_time: string;
  frame_number: number;
  object_name: string;
  confidence: number;
  tracking_id: number | null;
  timestamp: string;
  image_path: string;
}

export default function HistoryPage() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(15);
  const [isLoading, setIsLoading] = useState(false);
  const [objectFilter, setObjectFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [modalImage, setModalImage] = useState<string | null>(null);

  const fetchDetections = async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: perPage.toString(),
      });
      if (objectFilter) params.append("object_name", objectFilter);
      if (dateFilter) params.append("date", dateFilter);

      const res = await fetch(`http://localhost:5000/api/detections?${params}`);
      const data = await res.json();
      setDetections(data.data || []);
      setTotalCount(data.count || 0);
    } catch (e) {
      console.error("Error fetching detections:", e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDetections();
  }, [page, objectFilter, dateFilter]);

  const totalPages = Math.ceil(totalCount / perPage);

  const exportToExcel = () => {
    const rows = [
      ["ID", "Timestamp", "Frame Time", "Frame #", "Object", "Confidence", "Tracking ID", "Image URL"],
      ...detections.map((d) => [
        d.id,
        d.timestamp,
        d.frame_time,
        d.frame_number,
        d.object_name,
        d.confidence?.toFixed(3),
        d.tracking_id ?? "N/A",
        d.image_path || "-",
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Detection History");
    XLSX.writeFile(wb, `detection_history_page${page}.xlsx`);
  };

  const getObjectBadgeColor = (name: string) => {
    switch (name) {
      case "eating": return "bg-amber-50 text-amber-700 border-amber-200";
      case "sleep": return "bg-indigo-50 text-indigo-700 border-indigo-200";
      case "playing game phone": return "bg-rose-50 text-rose-700 border-rose-200";
      default: return "bg-slate-50 text-slate-600 border-slate-200";
    }
  };

  const getObjectEmoji = (name: string) => {
    switch (name) {
      case "eating": return "🍕";
      case "sleep": return "😴";
      case "playing game phone": return "📱";
      default: return "❓";
    }
  };

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#f0f4f8" }}>
      <Navbar isConnected={false} />

      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-8 py-6 space-y-6">
        {/* Page Header */}
        <div className="anim-in">
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2.5">
            <Clock size={24} className="text-sky-500" />
            Riwayat Deteksi
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Semua data deteksi pelanggaran yang tersimpan di database.
          </p>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 anim-in-1">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                <Filter size={11} className="inline mr-1" />Jenis Pelanggaran
              </label>
              <select
                value={objectFilter}
                onChange={(e) => { setObjectFilter(e.target.value); setPage(1); }}
                className="w-full px-3 py-2.5 border-2 border-slate-200 rounded-xl text-sm bg-slate-50 text-slate-800 outline-none focus:border-sky-400 focus:bg-white transition-all"
              >
                <option value="">Semua Jenis</option>
                <option value="eating">🍕 Eating</option>
                <option value="sleep">😴 Sleep</option>
                <option value="playing game phone">📱 Playing Game Phone</option>
              </select>
            </div>
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                <Search size={11} className="inline mr-1" />Tanggal
              </label>
              <input
                type="date"
                value={dateFilter}
                onChange={(e) => { setDateFilter(e.target.value); setPage(1); }}
                className="w-full px-3 py-2.5 border-2 border-slate-200 rounded-xl text-sm bg-slate-50 text-slate-800 outline-none focus:border-sky-400 focus:bg-white transition-all"
              />
            </div>
            <div className="flex gap-2">
              {(objectFilter || dateFilter) && (
                <button
                  onClick={() => { setObjectFilter(""); setDateFilter(""); setPage(1); }}
                  className="px-4 py-2.5 text-sm font-medium text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200 transition-colors"
                >
                  Reset Filter
                </button>
              )}
              {detections.length > 0 && (
                <button
                  onClick={exportToExcel}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 bg-emerald-500 text-white rounded-xl text-sm font-semibold hover:bg-emerald-600 transition-colors"
                >
                  <Download size={14} /> Export Excel
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Results Summary */}
        <div className="flex items-center justify-between text-sm text-slate-500 anim-in-2">
          <span>
            Menampilkan <strong className="text-slate-700">{detections.length}</strong> dari{" "}
            <strong className="text-slate-700">{totalCount}</strong> data
          </span>
          {totalPages > 0 && (
            <span>
              Halaman <strong className="text-slate-700">{page}</strong> / <strong className="text-slate-700">{totalPages}</strong>
            </span>
          )}
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden anim-in-2">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50 border-b-2 border-slate-200">
                  {["Timestamp", "Frame Time", "Frame #", "Jenis Pelanggaran", "Confidence", "Tracking ID", "Gambar"].map((h) => (
                    <th key={h} className="px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-14 text-center text-sm text-slate-400">
                      <div className="animate-pulse">Memuat data...</div>
                    </td>
                  </tr>
                ) : detections.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-14 text-center text-sm text-slate-400 italic">
                      Tidak ada data ditemukan.
                    </td>
                  </tr>
                ) : (
                  detections.map((det) => (
                    <tr key={det.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-3 text-xs text-slate-500">
                        {new Date(det.timestamp).toLocaleDateString("id-ID", {
                          day: "2-digit", month: "short", year: "numeric",
                        })}{" "}
                        <span className="text-slate-400">
                          {new Date(det.timestamp).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <span className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full bg-sky-50 text-sky-600">
                          {det.frame_time || "N/A"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-sm text-slate-700">{det.frame_number}</td>
                      <td className="px-5 py-3">
                        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${getObjectBadgeColor(det.object_name)}`}>
                          {getObjectEmoji(det.object_name)} {det.object_name}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <span className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                          {det.confidence ? (det.confidence * 100).toFixed(1) + "%" : "N/A"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-sm text-slate-500 font-mono">
                        {det.tracking_id ?? "—"}
                      </td>
                      <td className="px-5 py-3">
                        {det.image_path ? (
                          <img
                            src={det.image_path}
                            alt={`Detection ${det.id}`}
                            className="w-20 h-14 object-cover rounded-lg border-2 border-slate-200 cursor-pointer hover:scale-105 transition-transform"
                            onClick={() => setModalImage(det.image_path)}
                          />
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 py-4 border-t border-slate-200 bg-slate-50">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg text-slate-500 hover:bg-white hover:text-sky-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors border border-transparent hover:border-slate-200"
              >
                <ChevronLeft size={18} />
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (page <= 3) {
                  pageNum = i + 1;
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = page - 2 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`w-9 h-9 rounded-lg text-sm font-semibold transition-all ${
                      page === pageNum
                        ? "bg-sky-500 text-white shadow-md shadow-sky-500/30"
                        : "text-slate-500 hover:bg-white hover:text-sky-500 border border-transparent hover:border-slate-200"
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg text-slate-500 hover:bg-white hover:text-sky-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors border border-transparent hover:border-slate-200"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Modal */}
      {modalImage && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100] p-4" onClick={() => setModalImage(null)}>
          <div className="bg-white rounded-2xl max-w-[90vw] max-h-[90vh] overflow-auto p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <img src={modalImage} alt="Detail deteksi" className="w-full h-auto max-h-[75vh] object-contain rounded-xl" />
            <div className="mt-4 text-right">
              <button onClick={() => setModalImage(null)} className="inline-flex items-center gap-1.5 px-5 py-2 bg-red-500 text-white rounded-lg text-sm font-semibold hover:bg-red-600 transition-colors">
                <X size={14} /> Tutup
              </button>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
