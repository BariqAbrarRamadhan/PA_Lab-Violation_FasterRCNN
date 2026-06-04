"use client";

import { useEffect, useState } from "react";
import io, { Socket } from "socket.io-client";
import { UploadCloud, FileVideo, X, Download, Video, ClipboardList, StopCircle } from "lucide-react";
import * as XLSX from "xlsx";
import Link from "next/link";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";

interface DetectionLog {
  frame_time?: string;
  frame_number?: number;
  object_name?: string;
  confidence?: number;
  image_path?: string;
  message?: string;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [videoFrame, setVideoFrame] = useState<string | null>(null);
  const [logs, setLogs] = useState<DetectionLog[]>([]);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);

  useEffect(() => {
    const s = io("http://localhost:5000");
    s.on("connect", () => setIsConnected(true));
    s.on("disconnect", () => setIsConnected(false));
    s.on("video_frame", (data) => { setVideoFrame(`data:image/jpeg;base64,${data.frame}`); setIsDetecting(true); });
    s.on("detection_log", (data) => { setLogs((prev) => [...prev, data]); });
    s.on("video_done", (data) => { setToastMessage(data.message); setIsDetecting(false); setTimeout(() => setToastMessage(null), 5000); });
    s.on("violation_alert", (data) => {
      setToastMessage(`Pelanggaran: ${data.message} frame ke-${data.frame_number}`);
      setTimeout(() => setToastMessage(null), 5000);
      setLogs((prev) => [...prev, data]);
    });
    return () => { s.disconnect(); };
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setLogs([]); // Reset logs saat memulai video baru
    const fd = new FormData();
    fd.append("video", file);
    try {
      const res = await fetch("http://localhost:5000/upload_video", { method: "POST", body: fd });
      const data = await res.json();
      if (res.ok) setVideoFrame("");
      else alert("Error: " + data.error);
    } catch { alert("Gagal mengunggah video"); }
    finally { setIsUploading(false); }
  };

  const handleStop = async () => {
    try {
      await fetch("http://localhost:5000/stop_detection", { method: "POST" });
      setIsDetecting(false);
      setToastMessage("Deteksi dihentikan.");
      setTimeout(() => setToastMessage(null), 3000);
    } catch { console.error("Gagal menghentikan deteksi"); }
  };

  const exportToExcel = () => {
    const rows = [
      ["Frame Time", "Frame Number", "Object Name", "Confidence", "Image URL"],
      ...logs.map((l) => [l.frame_time || "N/A", l.frame_number || "N/A", l.object_name || "Unknown", l.confidence ? l.confidence.toFixed(2) : "N/A", l.image_path || "-"]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Detection Logs");
    XLSX.writeFile(wb, "detection_logs.xlsx");
  };

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#f0f4f8" }}>

      {/* ===== TOPBAR ===== */}
      <Navbar isConnected={isConnected} />

      {/* ===== MAIN ===== */}
      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-8 py-6 space-y-6">

        {/* -- TOP GRID: Upload & Preview -- */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* -- Upload Card (Left Column, Span 1) -- */}
          <div className="lg:col-span-1 bg-white rounded-2xl border border-slate-200 shadow-sm anim-in-1 flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center gap-2.5">
              <UploadCloud size={18} className="text-sky-500" />
              <h2 className="text-sm font-semibold text-slate-800">Upload Video</h2>
            </div>
            <div className="p-6 flex flex-col flex-1">
              <div
                className={`border-2 border-dashed rounded-xl py-10 px-6 text-center cursor-pointer transition-all flex-1 flex flex-col justify-center ${file
                    ? "border-sky-400 bg-sky-50"
                    : "border-slate-300 bg-slate-50 hover:border-sky-400 hover:bg-sky-50"
                  }`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => document.getElementById("video-upload")?.click()}
              >
                <div className="w-14 h-14 mx-auto mb-4 bg-sky-100 rounded-xl flex items-center justify-center">
                  <UploadCloud size={28} className="text-sky-500" />
                </div>
                <p className="text-base font-semibold text-slate-800 mb-1">Klik atau seret file video</p>
                <p className="text-sm text-slate-500 mt-2">Format: MP4, AVI, MOV<br/>Maks. 100MB</p>
                <input type="file" id="video-upload" accept="video/*" className="hidden" onChange={handleFileChange} />
              </div>

              {file && (
                <div className="mt-4 flex items-center justify-between gap-2 bg-sky-50 border border-sky-200 text-sky-700 text-sm font-medium px-4 py-2.5 rounded-xl">
                  <div className="flex items-center gap-2 overflow-hidden">
                    <FileVideo size={16} className="shrink-0" />
                    <span className="truncate max-w-[150px]">{file.name}</span>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); setFile(null); }} className="text-red-500 hover:bg-red-100 rounded-full p-1 transition-colors shrink-0">
                    <X size={14} />
                  </button>
                </div>
              )}

              <div className="mt-5 flex gap-2">
                <button
                  onClick={handleUpload}
                  disabled={!file || isUploading}
                  className="flex-1 inline-flex items-center justify-center gap-2 px-7 py-3 bg-sky-500 text-white rounded-xl text-sm font-semibold hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-sky-500/30 active:scale-[0.98]"
                >
                  <FileVideo size={16} />
                  {isUploading ? "Mengunggah..." : "Upload & Deteksi"}
                </button>
                {isDetecting && (
                  <button
                    onClick={handleStop}
                    className="inline-flex items-center justify-center gap-1.5 px-4 py-3 bg-red-500 text-white rounded-xl text-sm font-semibold hover:bg-red-600 transition-all hover:shadow-lg hover:shadow-red-500/30 active:scale-[0.98]"
                    title="Hentikan Deteksi"
                  >
                    <StopCircle size={16} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* -- Video Preview (Right Column, Span 2) -- */}
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm anim-in overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Video size={18} className="text-sky-500" />
                <h2 className="text-sm font-semibold text-slate-800">Live Preview</h2>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <div className={`w-2 h-2 rounded-full transition-all ${isDetecting ? "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.2)]" : "bg-slate-300"}`} />
                <span>{isDetecting ? "Deteksi berjalan..." : "Menunggu video..."}</span>
              </div>
            </div>
            <div className="flex items-center justify-center flex-1 bg-slate-900 overflow-hidden relative" style={{ minHeight: "420px" }}>
              {videoFrame === null ? (
                <div className="text-center py-20">
                  <Video size={56} className="mx-auto text-slate-600 mb-4" />
                  <p className="text-slate-500 text-base font-medium">Preview video akan muncul di sini</p>
                </div>
              ) : videoFrame === "" ? (
                <div className="text-center py-20 animate-pulse">
                  <Video size={56} className="mx-auto text-sky-500 mb-4" />
                  <p className="text-slate-400 text-base font-medium">Memuat video frame...</p>
                </div>
              ) : (
                <img src={videoFrame} alt="Video Frame" className="w-full h-full object-contain" />
              )}
            </div>
          </div>

        </div>

        {/* -- Detection Logs -- */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm anim-in-2 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <ClipboardList size={18} className="text-sky-500" />
              <h2 className="text-sm font-semibold text-slate-800">Detection Logs</h2>
              {logs.length > 0 && (
                <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-sky-100 text-sky-600">{logs.length}</span>
              )}
            </div>
            {logs.length > 0 && (
              <button onClick={exportToExcel} className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-emerald-500 text-white rounded-lg text-xs font-semibold hover:bg-emerald-600 transition-colors">
                <Download size={13} /> Export Excel
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50 border-b-2 border-slate-200">
                  {["Frame Time", "Frame #", "Objek", "Confidence", "Gambar"].map((h) => (
                    <th key={h} className="px-6 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-14 text-center text-sm text-slate-400 italic">
                      Belum ada deteksi. Upload video untuk memulai.
                    </td>
                  </tr>
                ) : (
                  logs.map((log, i) => (
                    <tr key={i} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-3">
                        <span className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full bg-sky-50 text-sky-600">{log.frame_time || "N/A"}</span>
                      </td>
                      <td className="px-6 py-3 text-sm text-slate-700">{log.frame_number || "N/A"}</td>
                      <td className="px-6 py-3 text-sm font-semibold text-slate-800">{log.object_name || "Unknown"}</td>
                      <td className="px-6 py-3">
                        <span className="inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                          {log.confidence ? (log.confidence * 100).toFixed(1) + "%" : "N/A"}
                        </span>
                      </td>
                      <td className="px-6 py-3">
                        {log.image_path ? (
                          <img
                            src={log.image_path.startsWith("http") ? log.image_path : `http://localhost:5000${log.image_path}`}
                            alt={`Frame ${log.frame_number}`}
                            className="w-20 h-14 object-cover rounded-lg border-2 border-slate-200 cursor-pointer hover:scale-105 transition-transform"
                            onClick={() => setModalImage(log.image_path!.startsWith("http") ? log.image_path! : `http://localhost:5000${log.image_path}`)}
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
        </div>
      </main>

      {/* ===== TOAST ===== */}
      {toastMessage && (
        <div className="fixed bottom-4 right-4 max-w-sm text-white px-5 py-3.5 rounded-xl z-50 flex items-start gap-3 border-l-4 border-red-500 text-sm shadow-2xl" style={{ background: "#0f172a" }}>
          <span className="flex-1">{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} className="text-slate-400 hover:text-white transition-colors shrink-0">
            <X size={16} />
          </button>
        </div>
      )}

      {/* ===== MODAL ===== */}
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
      {/* ===== FOOTER ===== */}
      <Footer />
    </div>
  );
}
