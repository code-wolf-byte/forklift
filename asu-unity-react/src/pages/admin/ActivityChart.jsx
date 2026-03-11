import { useRef, useEffect } from "react";
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";

Chart.register(
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Filler
);

function fmtLabel(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

// datasets: [{ data: [{date, count}], label, color }]
export default function ActivityChart({ datasets, isDark }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  const hasData = datasets?.some((ds) => ds.data?.length > 0);

  useEffect(() => {
    if (!hasData || !canvasRef.current) return;
    if (chartRef.current) chartRef.current.destroy();

    const ctx = canvasRef.current.getContext("2d");
    const chartHeight = canvasRef.current.offsetHeight || 280;
    const alpha = isDark ? 0.45 : 0.3;

    // Union of all dates across every series, sorted
    const dateSet = new Set();
    datasets.forEach((ds) => ds.data?.forEach((d) => dateSet.add(d.date)));
    const allDates = [...dateSet].sort();

    const chartDatasets = datasets.map((ds) => {
      const map = Object.fromEntries((ds.data || []).map((d) => [d.date, d.count]));
      const rgb = hexToRgb(ds.color);
      const gradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
      gradient.addColorStop(0, `rgba(${rgb},${alpha})`);
      gradient.addColorStop(1, `rgba(${rgb},0)`);
      return {
        label: ds.label,
        data: allDates.map((date) => map[date] ?? 0),
        borderColor: ds.color,
        borderWidth: 2,
        backgroundColor: gradient,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: ds.color,
        pointHoverBorderColor: "#fff",
        pointHoverBorderWidth: 2,
      };
    });

    const tickColor = isDark ? "#909296" : "#6c757d";
    const gridColor = isDark ? "#2b2d31" : "#e9ecef";
    const multi = datasets.length > 1;

    chartRef.current = new Chart(ctx, {
      type: "line",
      data: {
        labels: allDates.map(fmtLabel),
        datasets: chartDatasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: {
            display: multi,
            labels: {
              color: isDark ? "#dcddde" : "#4e5058",
              boxWidth: 12,
              padding: 12,
              usePointStyle: true,
              pointStyleWidth: 10,
            },
          },
          tooltip: {
            displayColors: multi,
            callbacks: {
              title: (items) => allDates[items[0].dataIndex] ?? items[0].label,
              label: (item) =>
                multi
                  ? `${item.dataset.label}: ${item.parsed.y}`
                  : `${item.parsed.y}`,
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
  }, [datasets, isDark, hasData]);

  if (!hasData) {
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
