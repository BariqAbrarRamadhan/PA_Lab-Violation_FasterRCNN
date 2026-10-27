"use client";

import { useEffect, useState, useRef } from "react";
import io, { Socket } from "socket.io-client";
import { Link2, ClipboardPaste, X, Video, ClipboardList, Download, StopCircle, Activity } from "lucide-react";
import * as XLSX from "xlsx";
import Link from "next/link";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";

interface DetectionLog {
  frame_time?: string;
  frame_number?: number;
  object_name?: string;
  confidence?: number;
  image_path?: string;
  message?: string;
  tracking_id?: number | string;
}

interface StreamMetrics {
  fps_actual: number;
  inference_ms: number;
  cpu_percent: number;
  ram_mb: number;
  gpu_percent: number;
  frame_number: number;
  uptime_seconds: number;
  detections_count: number;
  status: string;
}

export default function UrlPage() {
  const [url, setUrl] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [logs, setLogs] = useState<DetectionLog[]>([]);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  
  const [metrics, setMetrics] = useState<StreamMetrics | null>(null);
  const [apiHost, setApiHost] = useState("http://localhost:5000");
  const [frontendUrl, setFrontendUrl] = useState("http://localhost:3000/url");

  useEffect(() => {
    // Gunakan hostname yang sama dengan frontend agar bisa diakses via LAN
    const host = typeof window !== "undefined" ? `http://${window.location.hostname}:5000` : "http://localhost:5000";
    setApiHost(host);
    if (typeof window !== "undefined") {
      setFrontendUrl(`http://${window.location.hostname}:3000/url`);
    }

    const s = io(host);
    s.on("connect", () => setIsConnected(true));
    s.on("disconnect", () => {
      setIsConnected(false);
      if (isDetecting) setToastMessage("Koneksi ke server terputus...");
    });
    
    // Menerima metrik performa
    s.on("stream_metrics", (data: StreamMetrics) => {
      setMetrics(data);
      if (data.status === "active") setIsDetecting(true);
    });

    s.on("video_done", (data) => {
      setIsDetecting(false);
      setToastMessage(data.message || "Stream dihentikan.");
      setTimeout(() => setToastMessage(null), 5000);
    });

    s.on("violation_alert", (data) => {
      setToastMessage(`Pelanggaran: ${data.object_name} frame ke-${data.frame_number}`);
      setTimeout(() => setToastMessage(null), 5000);
      setLogs((prev) => [data, ...prev]); // Prepend agar yang terbaru di atas
    });

    return () => { s.disconnect(); };
  }, [isDetecting]);

  const handlePaste = async () => {
    try { setUrl(await navigator.clipboard.readText()); }
    catch (e) { console.error("Clipboard error:", e); }
  };

  const handleSubmit = async () => {
    if (!url.trim()) { alert("Masukkan URL yang valid"); return; }
    setIsProcessing(true);
    setLogs([]); // Reset logs saat memulai stream baru
    setMetrics(null);
    try {
      const res = await fetch(`${apiHost}/detect_from_stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stream_url: url.trim() }),
      });
      const data = await res.json();
      if (data.stream_url) {
        setIsDetecting(true);
      } else {
        alert("Gagal memproses stream");
      }
    } catch { alert("Gagal memproses stream"); }
    finally { setIsProcessing(false); }
  };

  const handleStop = async () => {
    try {
      await fetch(`${apiHost}/stop_stream`, { method: "POST" });
      setIsDetecting(false);
    } catch { console.error("Gagal menghentikan deteksi"); }
  };

  const exportToExcel = () => {
    const rows = [
      ["Frame Time", "Frame Number", "Object Name", "Confidence", "Tracking ID", "Image URL"],
      ...logs.map((l) => [
        l.frame_time || "N/A", 
        l.frame_number || "N/A", 
        l.object_name || "Unknown", 
        l.confidence ? (l.confidence * 100).toFixed(1) + "%" : "N/A", 
        l.tracking_id || "-",
        l.image_path || "-"
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Detection Logs");
    XLSX.writeFile(wb, `stream_detection_logs_${new Date().toISOString().slice(0,10)}.xlsx`);
  };

  const formatUptime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return [h,m,s].map(v => String(v).padStart(2,'0')).join(':');
  };

  const getStatusColor = (status?: string) => {
    if (status === "active") return "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.2)] animate-pulse";
    if (status === "connecting" || status === "reconnecting") return "bg-amber-500 animate-pulse";
    return "bg-slate-300";
  };

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#f0f4f8" }}>
      <Navbar isConnected={isConnected} />

      <main className="flex-1 w-full max-w-[1400px] mx-auto px-4 md:px-8 py-6 space-y-6">
        
        {/* Banner Info LAN */}
        <div className="bg-gradient-to-r from-sky-50 to-cyan-50 border border-sky-200 rounded-xl p-4 flex gap-3 items-start anim-in">
          <Activity size={20} className="text-sky-500 shrink-0 mt-0.5" />
          <div className="text-sm text-slate-700">
            Untuk mengakses dari perangkat lain di <strong>Wifi Kampus</strong>, pastikan menggunakan alamat dengan IP server 
            <span className="ml-1 font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-sky-600">
              {frontendUrl}
            </span>.
            <br />Pastikan kamera CCTV dan server terhubung ke jaringan yang sama.
          </div>
        </div>

        {/* -- TOP GRID: Upload & Preview -- */}
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">

          {/* KIRI: Stream URL + Preview */}
          <div className="flex flex-col gap-6">
            
            {/* -- URL Input Card -- */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm anim-in flex flex-col">
              <div className="px-6 py-4 border-b border-slate-200 flex items-center gap-2.5">
                <Link2 size={18} className="text-sky-500" />
                <h2 className="text-sm font-semibold text-slate-800">Stream URL</h2>
              </div>
              <div className="p-6">
                <label htmlFor="streamingUrl" className="block text-sm font-medium text-slate-700 mb-2">
                  URL Video / RTSP Stream
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="url"
                    id="streamingUrl"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="rtsp://user:pass@ip-kamera/stream atau https://example.com/video.mp4"
                    className="flex-1 px-4 py-3 border-2 border-slate-200 rounded-xl text-sm bg-slate-50 text-slate-800 placeholder:text-slate-400 outline-none focus:border-sky-400 focus:bg-white focus:ring-2 focus:ring-sky-100 transition-all min-w-0 font-mono"
                  />
                  <button
                    onClick={handlePaste}
                    title="Tempel dari clipboard"
                    className="w-12 h-12 flex items-center justify-center bg-slate-50 border-2 border-slate-200 rounded-xl hover:bg-sky-500 hover:border-sky-500 group transition-all shrink-0"
                  >
                    <ClipboardPaste size={16} className="text-slate-400 group-hover:text-white transition-colors" />
                  </button>
                </div>
                
                <div className="flex flex-wrap gap-2 mb-6">
                  {["rtsp://", "rtsp://admin:password@", "http://", "https://"].map((p, idx) => (
                    <button
                      key={idx}
                      onClick={() => setUrl(p)}
                      className="px-3 py-1.5 bg-slate-100 border border-slate-200 rounded-full text-xs font-medium text-slate-600 hover:bg-sky-50 hover:border-sky-300 hover:text-sky-600 transition-all font-mono"
                    >
                      {idx === 0 ? "📹 RTSP Stream" : idx === 1 ? "🔐 RTSP+Auth" : idx === 2 ? "🌐 HTTP" : "🔒 HTTPS"}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-3">
                  {!isDetecting ? (
                    <button
                      onClick={handleSubmit}
                      disabled={isProcessing || !url.trim()}
                      className="inline-flex items-center justify-center gap-2 px-7 py-3 bg-sky-500 text-white rounded-xl text-sm font-semibold hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-sky-500/30"
                    >
                      <Link2 size={16} />
                      {isProcessing ? "Menghubungkan..." : "Mulai Deteksi"}
                    </button>
                  ) : (
                    <button
                      onClick={handleStop}
                      className="inline-flex items-center justify-center gap-2 px-7 py-3 bg-red-500 text-white rounded-xl text-sm font-semibold hover:bg-red-600 transition-all hover:shadow-lg hover:shadow-red-500/30"
                    >
                      <StopCircle size={16} />
                      Stop Stream
                    </button>
                  )}
                  
                  {isDetecting && (
                    <a
                      href={`${apiHost}/api/stream_metrics/export`}
                      target="_blank"
                      className="inline-flex items-center justify-center gap-2 px-5 py-3 bg-white border-2 border-slate-200 text-slate-600 rounded-xl text-sm font-semibold hover:border-sky-400 hover:text-sky-600 transition-all"
                    >
                      <Download size={16} />
                      Export Perf CSV
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* -- Video Preview -- */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm anim-in-1 overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Video size={18} className="text-sky-500" />
                  <h2 className="text-sm font-semibold text-slate-800">Live Preview</h2>
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500 font-medium">
                  {metrics?.fps_actual ? <span className="font-mono text-sky-600 bg-sky-50 px-2 py-0.5 rounded">{metrics.fps_actual.toFixed(1)} fps</span> : null}
                  <div className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-full transition-all ${getStatusColor(metrics?.status)}`} />
                    <span>
                      {metrics?.status === 'active' ? 'Stream aktif' : 
                       metrics?.status === 'connecting' ? 'Menghubungkan...' : 
                       metrics?.status === 'reconnecting' ? 'Reconnecting...' : 'Menunggu stream...'}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-center bg-slate-900 overflow-hidden relative" style={{ minHeight: "480px" }}>
                {!isDetecting ? (
                  <div className="text-center py-20">
                    <Video size={56} className="mx-auto text-slate-600 mb-4" />
                    <p className="text-slate-500 text-base font-medium">Preview stream akan muncul di sini</p>
                  </div>
                ) : (
                  <img src={`${apiHost}/video_feed?t=${Date.now()}`} alt="Live Stream" className="w-full h-full object-contain" />
                )}
              </div>
            </div>

          </div>

          {/* KANAN: Performance Monitor */}
          <div className="flex flex-col gap-6">
            
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm anim-in-1 flex flex-col">
              <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Activity size={18} className="text-emerald-500" />
                  <h2 className="text-sm font-semibold text-slate-800">Perf Monitor</h2>
                </div>
                <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-1 rounded">
                  {metrics ? formatUptime(metrics.uptime_seconds) : "00:00:00"}
                </span>
              </div>
              
              <div className="p-5 grid grid-cols-2 gap-4">
                
                {/* FPS */}
                <div className={`rounded-xl border p-3 text-center transition-colors ${!metrics ? 'border-slate-100 bg-slate-50' : metrics.fps_actual < 1 ? 'border-red-200 bg-red-50' : metrics.fps_actual < 5 ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Actual FPS</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics ? metrics.fps_actual.toFixed(1) : "—"}</div>
                  <div className="w-full h-1 bg-slate-100 rounded-full mt-3 overflow-hidden">
                    <div className="h-full bg-emerald-500 transition-all duration-500" style={{ width: metrics ? `${Math.min(metrics.fps_actual / 30 * 100, 100)}%` : '0%' }} />
                  </div>
                </div>

                {/* Inference */}
                <div className={`rounded-xl border p-3 text-center transition-colors ${!metrics ? 'border-slate-100 bg-slate-50' : metrics.inference_ms > 1000 ? 'border-red-200 bg-red-50' : metrics.inference_ms > 500 ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Inference</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics ? metrics.inference_ms.toFixed(0) : "—"}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">ms / frame</div>
                </div>

                {/* CPU */}
                <div className={`rounded-xl border p-3 text-center transition-colors ${!metrics ? 'border-slate-100 bg-slate-50' : metrics.cpu_percent > 90 ? 'border-red-200 bg-red-50' : metrics.cpu_percent > 75 ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">CPU Usage</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics ? metrics.cpu_percent.toFixed(0) : "—"}<span className="text-sm text-slate-400 ml-0.5">%</span></div>
                  <div className="w-full h-1 bg-slate-100 rounded-full mt-3 overflow-hidden">
                    <div className="h-full bg-sky-500 transition-all duration-500" style={{ width: metrics ? `${metrics.cpu_percent}%` : '0%' }} />
                  </div>
                </div>

                {/* RAM */}
                <div className={`rounded-xl border p-3 text-center transition-colors ${!metrics ? 'border-slate-100 bg-slate-50' : metrics.ram_mb > 6000 ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'}`}>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">RAM Used</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics ? metrics.ram_mb.toFixed(0) : "—"}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">MB</div>
                </div>

                {/* GPU */}
                <div className={`rounded-xl border p-3 text-center transition-colors ${!metrics ? 'border-slate-100 bg-slate-50' : metrics.gpu_percent > 90 ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'}`}>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">GPU Usage</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics && metrics.gpu_percent > 0 ? metrics.gpu_percent.toFixed(0) : "N/A"}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">%</div>
                </div>

                {/* Frames */}
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Frames</div>
                  <div className="text-2xl font-bold text-slate-800 font-mono leading-none">{metrics ? metrics.frame_number : "—"}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">diproses</div>
                </div>

              </div>
              <div className="bg-slate-50 p-4 border-t border-slate-100 text-[11px] text-slate-500 text-center">
                Metrik dicatat ke CSV setiap detik untuk analisis beban server.
              </div>
            </div>

            {/* -- Detection Logs Mini -- */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm anim-in-2 flex-1 flex flex-col overflow-hidden min-h-[400px]">
              <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ClipboardList size={16} className="text-sky-500" />
                  <h2 className="text-sm font-semibold text-slate-800">Logs ({logs.length})</h2>
                </div>
                {logs.length > 0 && (
                  <button onClick={exportToExcel} className="text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 p-1.5 rounded-lg transition-colors" title="Export Excel">
                    <Download size={16} />
                  </button>
                )}
              </div>
              
              <div className="overflow-y-auto flex-1 p-2" style={{ maxHeight: "calc(100vh - 400px)", minHeight: "400px" }}>
                {logs.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-slate-400 italic text-sm">
                    Belum ada deteksi
                  </div>
                ) : (
                  <div className="space-y-2">
                    {logs.map((log, i) => (
                      <div key={i} className="bg-slate-50 border border-slate-100 rounded-xl p-3 hover:border-sky-200 transition-colors">
                        <div className="flex justify-between items-start mb-2">
                          <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-600 font-mono">
                            {log.frame_time}
                          </span>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                            {(log.confidence! * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="font-semibold text-sm text-slate-800 mb-2">
                          {log.object_name} <span className="text-xs font-normal text-slate-400 ml-1">ID:{log.tracking_id || '-'}</span>
                        </div>
                        {log.image_path && (
                          <img
                            src={log.image_path.startsWith("http") ? log.image_path : `${apiHost}${log.image_path}`}
                            alt="Bukti"
                            className="w-full h-24 object-cover rounded-lg border border-slate-200 cursor-pointer"
                            onClick={() => setModalImage(log.image_path!.startsWith("http") ? log.image_path! : `${apiHost}${log.image_path}`)}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

          </div>

        </div>
      </main>

      {/* ===== TOAST ===== */}
      {toastMessage && (
        <div className="fixed bottom-4 right-4 max-w-sm text-white px-5 py-3.5 rounded-xl z-50 flex items-start gap-3 border-l-4 border-sky-500 text-sm shadow-2xl" style={{ background: "#0f172a" }}>
          <span className="flex-1">{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} className="text-slate-400 hover:text-white transition-colors shrink-0">
            <X size={16} />
          </button>
        </div>
      )}

      {/* ===== MODAL ===== */}
      {modalImage && (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4" onClick={() => setModalImage(null)}>
          <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <h3 className="font-semibold text-slate-800">Detail Pelanggaran</h3>
              <button onClick={() => setModalImage(null)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-slate-900 flex items-center justify-center">
              <img src={modalImage} alt="Detail deteksi" className="w-full h-auto max-h-[70vh] object-contain rounded-xl" />
            </div>
          </div>
        </div>
      )}
      
      <Footer />
    </div>
  );
}
