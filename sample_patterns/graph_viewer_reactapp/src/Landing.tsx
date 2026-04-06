// Landing.tsx
import React from "react";
import CustomerGraphViewer from "./CustomerGraphViewer.tsx";
import ChatUI from "./ChatUI";

// Landing.tsx (replace your styles block)
const styles = `
  :root { /* ... */ }

  * { box-sizing: border-box; }
  html, body, #root { height:100%; width:100%; margin:0; padding:0; }

  .page {
    position: fixed;        /* take the whole viewport */
    inset: 0;               /* top/right/bottom/left = 0 */
    display: grid;
    grid-template-columns: minmax(0,0.4fr) minmax(0,0.6fr);
    gap: 5px;              /* keep only the space BETWEEN columns */
    padding: 0;             /* no outer padding */
    margin: 0;              /* no outer margin */
  }
`;


export default function LandingPage() {
  return (
    <div className="page">
      <style>{styles}</style>

      {/* Left 40% */}
      <section className="rounded-none border border-white/10 bg-white/[0.06] shadow-2xl overflow-hidden flex flex-col min-h-0">

        <div className="px-4 py-3 border-b border-white/10 bg-white/[0.04]">
          <h2 className="text-sm font-semibold tracking-tight text-slate-200">Graph Viewer</h2>
        </div>
        <div className="flex-1 min-h-0">
          <CustomerGraphViewer />
        </div>
      </section>

      {/* Right 60% */}
      <section className="rounded-none border border-white/10 bg-white/[0.06] shadow-2xl overflow-hidden flex flex-col min-h-0">

        <div className="px-4 py-3 border-b border-white/10 bg-white/[0.04]">
          <h2 className="text-sm font-semibold tracking-tight text-slate-200">Chat with Knowledge Graph</h2>
        </div>
        <div className="flex-1 min-h-0">
          <ChatUI />
        </div>
      </section>
    </div>
  );
}
