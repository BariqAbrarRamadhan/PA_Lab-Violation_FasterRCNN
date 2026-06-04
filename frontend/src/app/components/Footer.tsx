import { Video } from "lucide-react";

export default function Footer() {
  return (
    <footer
      className="text-center text-xs py-4 border-t border-slate-200 mt-auto"
      style={{ background: "#f8fafc", color: "#64748b" }}
    >
      <div className="flex items-center justify-center gap-2 mb-1">
        <div className="w-5 h-5 bg-sky-500 rounded flex items-center justify-center">
          <Video size={10} className="text-white" />
        </div>
        <span className="font-semibold text-slate-700">SafeVision Lab</span>
      </div>
      <p>
        Sistem Deteksi Pelanggaran Peraturan Laboratorium &bull; Faster R-CNN
      </p>
      <p className="mt-0.5 text-slate-400">
        &copy; {new Date().getFullYear()} &mdash; All rights reserved.
      </p>
    </footer>
  );
}
