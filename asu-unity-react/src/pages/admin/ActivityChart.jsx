import { useRef, useEffect } from "react";
import {
  Chart,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
} from "chart.js";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

function fmtLabel(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function ActivityChart({ data, label, isDark }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!data || !canvasRef.current) return;
    if (chartRef.current) chartRef.current.destroy();

    const tickColor  = isDark ? "#909296" : "#6c757d";
    const gridColor  = isDark ? "#2b2d31" : "#e9ecef";
    const barColor   = isDark ? "rgba(140,29,64,0.75)" : "rgba(140,29,64,0.65)";
    const barBorder  = "#8c1d40";

    chartRef.current = new Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: data.map((d) => fmtLabel(d.date)),
        datasets: [
          {
            label,
            data: data.map((d) => d.count),
            backgroundColor: barColor,
            borderColor: barBorder,
            borderWidth: 1,
            borderRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => data[items[0].dataIndex]?.date ?? items[0].label,
            },
          },
        },
        scales: {
          x: {
            grid: { color: gridColor },
            ticks: { color: tickColor, maxTicksLimit: 14, maxRotation: 0 },
          },
          y: {
            beginAtZero: true,
            grid: { color: gridColor },
            ticks: { color: tickColor, stepSize: 1, precision: 0 },
          },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [data, label, isDark]);

  if (!data || data.length === 0) {
    return (
      <div
        className="d-flex align-items-center justify-content-center text-muted small"
        style={{ height: 180 }}
      >
        No data for selected range.
      </div>
    );
  }

  return (
    <div style={{ height: 200, position: "relative" }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
