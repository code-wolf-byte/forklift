import { useRef, useEffect } from "react";
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Filler,
} from "chart.js";

Chart.register(
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Filler
);

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

    const ctx = canvasRef.current.getContext("2d");
    const chartHeight = canvasRef.current.offsetHeight || 220;

    // Statbot-style gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
    if (isDark) {
      gradient.addColorStop(0, "rgba(140,29,64,0.45)");
      gradient.addColorStop(1, "rgba(140,29,64,0)");
    } else {
      gradient.addColorStop(0, "rgba(140,29,64,0.3)");
      gradient.addColorStop(1, "rgba(140,29,64,0)");
    }

    const tickColor = isDark ? "#909296" : "#6c757d";
    const gridColor = isDark ? "#2b2d31" : "#e9ecef";

    chartRef.current = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.map((d) => fmtLabel(d.date)),
        datasets: [
          {
            label,
            data: data.map((d) => d.count),
            borderColor: "#8c1d40",
            borderWidth: 2,
            backgroundColor: gradient,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: "#8c1d40",
            pointHoverBorderColor: "#fff",
            pointHoverBorderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          intersect: false,
          mode: "index",
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: (items) => data[items[0].dataIndex]?.date ?? items[0].label,
              label: (item) => `${item.parsed.y} ${label.toLowerCase()}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: gridColor, drawBorder: false },
            ticks: { color: tickColor, maxTicksLimit: 10, maxRotation: 0 },
            border: { display: false },
          },
          y: {
            beginAtZero: true,
            grid: { color: gridColor, drawBorder: false },
            ticks: { color: tickColor, precision: 0 },
            border: { display: false },
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
      <div className="admin-chart-container d-flex align-items-center justify-content-center text-muted small">
        No data for selected range.
      </div>
    );
  }

  return (
    <div className="admin-chart-container">
      <canvas ref={canvasRef} />
    </div>
  );
}
