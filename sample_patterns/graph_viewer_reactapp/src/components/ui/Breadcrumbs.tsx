import React from "react";
import type { NavLevel } from "@/graph/types";

type Props = {
  levels: NavLevel[];
  currentIndex: number;
  onJump: (index: number) => void;
};

export default function Breadcrumbs({ levels, currentIndex, onJump }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px",
        background: "rgba(11,18,32,0.85)",
        color: "#cbd5e1",
        borderBottom: "1px solid #1f2937",
        position: "sticky",
        top: 0,
        zIndex: 10,
        backdropFilter: "blur(6px)",
      }}
    >
      {levels.map((lvl, i) => (
        <span key={`${lvl.title}-${i}`} style={{ display: "inline-flex", alignItems: "center" }}>
          <button
            onClick={() => onJump(i)}
            disabled={i === currentIndex}
            title={lvl.title}
            style={{
              cursor: i === currentIndex ? "default" : "pointer",
              border: "none",
              background: "transparent",
              padding: "2px 6px",
              fontSize: 13,
              color: i === currentIndex ? "#e5e7eb" : "#93c5fd",
              textDecoration: i === currentIndex ? "none" : "underline",
              borderRadius: 6,
            }}
          >
            {i === 0 ? "All" : lvl.title}
          </button>
          {i < levels.length - 1 && <span style={{ margin: "0 6px", opacity: 0.6 }}>›</span>}
        </span>
      ))}
    </div>
  );
}
