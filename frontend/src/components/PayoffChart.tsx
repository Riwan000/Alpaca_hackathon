import React, { useState } from 'react';
import type { PayoffPoint } from '../api/types';

export interface PayoffPointLike {
  price?: number;
  pnl?: number;
  x?: number;
  y?: number;
}

export interface PayoffChartProps {
  points?: (PayoffPoint | PayoffPointLike)[];
  currentPrice?: number;
  strikePrice?: number;
  strategyName?: string;
  height?: number;
  className?: string;
  showZeroLine?: boolean;
}

export const PayoffChart: React.FC<PayoffChartProps> = ({
  points = [],
  currentPrice,
  strikePrice,
  strategyName,
  height = 240,
  className = '',
  showZeroLine = true,
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<{ x: number; y: number; price: number; pnl: number } | null>(null);

  // Normalize points to { price, pnl }
  const normalizedPoints: { price: number; pnl: number }[] = points
    .map((p) => {
      const point = p as PayoffPointLike & PayoffPoint;
      return {
        price: point.price ?? point.x ?? 0,
        pnl: point.pnl ?? point.y ?? 0,
      };
    })
    .sort((a, b) => a.price - b.price);

  if (normalizedPoints.length === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center border border-[var(--border-color)] bg-[var(--bg-card)] p-6 text-center text-xs font-mono text-[var(--text-muted)] ${className}`}
        style={{ height }}
        data-testid="payoff-chart-placeholder"
      >
        <span className="mb-1 text-sm font-bold text-[var(--text-main)]">Payoff Profile</span>
        <span>No payoff data available for this strategy structure.</span>
      </div>
    );
  }

  // Calculate bounding boxes and viewbox coordinates
  const padding = { top: 24, right: 32, bottom: 32, left: 56 };
  const width = 600; // Reference internal coordinate width

  const prices = normalizedPoints.map((p) => p.price);
  const pnls = normalizedPoints.map((p) => p.pnl);

  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice === minPrice ? 1 : maxPrice - minPrice;

  const rawMinPnl = Math.min(0, ...pnls);
  const rawMaxPnl = Math.max(0, ...pnls);
  const pnlPadding = (rawMaxPnl - rawMinPnl) * 0.1 || 1000;
  const minPnl = rawMinPnl - pnlPadding;
  const maxPnl = rawMaxPnl + pnlPadding;
  const pnlRange = maxPnl === minPnl ? 1 : maxPnl - minPnl;

  const scaleX = (price: number) => {
    return padding.left + ((price - minPrice) / priceRange) * (width - padding.left - padding.right);
  };

  const scaleY = (pnl: number) => {
    return padding.top + (1 - (pnl - minPnl) / pnlRange) * (height - padding.top - padding.bottom);
  };

  // Generate SVG path
  const pathD = normalizedPoints.reduce((acc, point, idx) => {
    const x = scaleX(point.price);
    const y = scaleY(point.pnl);
    return `${acc} ${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)},${y.toFixed(1)}`;
  }, '');

  // Generate Area under curve down to y=scaleY(0)
  const zeroY = scaleY(0);
  const firstPoint = normalizedPoints[0];
  const lastPoint = normalizedPoints[normalizedPoints.length - 1];
  const areaD = `${pathD} L ${scaleX(lastPoint.price).toFixed(1)},${zeroY.toFixed(1)} L ${scaleX(firstPoint.price).toFixed(1)},${zeroY.toFixed(1)} Z`;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
      signDisplay: 'always',
    }).format(val);
  };

  const formatPrice = (val: number) => `$${val.toFixed(0)}`;

  // Tick marks
  const yTicks = [
    maxPnl,
    maxPnl / 2,
    0,
    minPnl / 2,
    minPnl,
  ].filter((val, i, arr) => arr.indexOf(val) === i);

  return (
    <div
      className={`relative border border-[var(--border-color)] bg-[var(--bg-card)] p-3 select-none ${className}`}
      data-testid="payoff-chart"
    >
      {strategyName && (
        <div className="flex justify-between items-center mb-2 px-1 text-xs font-mono">
          <span className="font-bold text-[var(--text-main)]">{strategyName} Payoff Profile</span>
          <span className="text-[10px] text-[var(--text-muted)]">EXPIRATION PAYOFF CURVE</span>
        </div>
      )}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible font-mono text-[10px]"
        style={{ maxHeight: height }}
      >
        <defs>
          <linearGradient id="payoffGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-spruce)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="var(--brand-spruce)" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Grid lines & Y-Axis Labels */}
        {yTicks.map((tick, i) => {
          const y = scaleY(tick);
          if (y < padding.top || y > height - padding.bottom) return null;
          const isZero = Math.abs(tick) < 0.01;
          return (
            <g key={i}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke={isZero && showZeroLine ? 'var(--text-main)' : 'var(--border-color)'}
                strokeWidth={isZero && showZeroLine ? 1.5 : 1}
                strokeDasharray={isZero ? undefined : '3,3'}
                strokeOpacity={isZero ? 0.8 : 0.6}
              />
              <text
                x={padding.left - 6}
                y={y + 3}
                textAnchor="end"
                fill="var(--text-muted)"
                className="text-[9px]"
              >
                {formatCurrency(tick)}
              </text>
            </g>
          );
        })}

        {/* Current Spot Price Reference Line */}
        {currentPrice && currentPrice >= minPrice && currentPrice <= maxPrice && (
          <g data-testid="current-price-indicator">
            <line
              x1={scaleX(currentPrice)}
              y1={padding.top}
              x2={scaleX(currentPrice)}
              y2={height - padding.bottom}
              stroke="var(--brand-teal)"
              strokeWidth={1.5}
              strokeDasharray="4,4"
            />
            <text
              x={scaleX(currentPrice)}
              y={padding.top - 6}
              textAnchor="middle"
              fill="var(--brand-teal)"
              className="text-[9px] font-bold"
            >
              Spot: {formatPrice(currentPrice)}
            </text>
          </g>
        )}

        {/* Strike Price Reference */}
        {strikePrice && strikePrice >= minPrice && strikePrice <= maxPrice && strikePrice !== currentPrice && (
          <g data-testid="strike-price-indicator">
            <line
              x1={scaleX(strikePrice)}
              y1={padding.top}
              x2={scaleX(strikePrice)}
              y2={height - padding.bottom}
              stroke="var(--brand-gold)"
              strokeWidth={1.5}
              strokeDasharray="2,2"
            />
            <text
              x={scaleX(strikePrice)}
              y={padding.top - 6}
              textAnchor="middle"
              fill="var(--brand-gold)"
              className="text-[9px] font-bold"
            >
              Strike: {formatPrice(strikePrice)}
            </text>
          </g>
        )}

        {/* Area Fill */}
        <path d={areaD} fill="url(#payoffGradient)" />

        {/* Payoff Curve Path */}
        <path
          d={pathD}
          fill="none"
          stroke="var(--brand-spruce)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          data-testid="payoff-curve-path"
        />

        {/* Interactive Data Points */}
        {normalizedPoints.map((point, idx) => {
          const cx = scaleX(point.price);
          const cy = scaleY(point.pnl);
          const isHovered = hoveredPoint?.price === point.price;
          return (
            <g
              key={idx}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredPoint({ x: cx, y: cy, price: point.price, pnl: point.pnl })}
              onMouseLeave={() => setHoveredPoint(null)}
            >
              <circle
                cx={cx}
                cy={cy}
                r={isHovered ? 5 : 3}
                fill={point.pnl >= 0 ? 'var(--brand-spruce)' : 'var(--status-danger)'}
                stroke="var(--bg-card)"
                strokeWidth={1.5}
                data-testid={`payoff-point-${idx}`}
              />
            </g>
          );
        })}

        {/* X-Axis Price Labels */}
        {normalizedPoints.map((point, idx) => {
          const x = scaleX(point.price);
          return (
            <text
              key={idx}
              x={x}
              y={height - padding.bottom + 16}
              textAnchor="middle"
              fill="var(--text-muted)"
              className="text-[9px]"
            >
              {formatPrice(point.price)}
            </text>
          );
        })}
      </svg>

      {/* Floating Hover Tooltip */}
      {hoveredPoint && (
        <div
          className="absolute z-10 p-2 bg-[var(--bg-card)] border border-[var(--brand-spruce)] shadow-sm text-xs font-mono pointer-events-none"
          style={{
            left: `${(hoveredPoint.x / width) * 100}%`,
            top: `${(hoveredPoint.y / height) * 100}%`,
            transform: 'translate(-50%, -120%)',
          }}
          data-testid="payoff-tooltip"
        >
          <div className="text-[10px] text-[var(--text-muted)]">Underlying: ${hoveredPoint.price.toFixed(2)}</div>
          <div className={`font-bold ${hoveredPoint.pnl >= 0 ? 'text-[var(--status-safe)]' : 'text-[var(--status-danger)]'}`}>
            P&L: {formatCurrency(hoveredPoint.pnl)}
          </div>
        </div>
      )}
    </div>
  );
};
