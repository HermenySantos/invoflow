'use client';

import React, { useState } from 'react';
import { AlertCircle, CheckCircle, HelpCircle } from 'lucide-react';

interface ConfidenceBadgeProps {
  confidence: number | null | undefined;
  fieldName?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

type ConfidenceLevel = 'high' | 'medium' | 'low' | 'unknown';

function getConfidenceLevel(confidence: number | null | undefined): ConfidenceLevel {
  if (confidence === null || confidence === undefined) return 'unknown';
  if (confidence >= 80) return 'high';
  if (confidence >= 50) return 'medium';
  return 'low';
}

function getConfidenceConfig(level: ConfidenceLevel) {
  switch (level) {
    case 'high':
      return {
        icon: CheckCircle,
        bgColor: 'bg-green-100',
        textColor: 'text-green-700',
        iconColor: 'text-green-600',
        label: 'Confiança alta',
        description: 'A leitura deste valor é fiável',
      };
    case 'medium':
      return {
        icon: AlertCircle,
        bgColor: 'bg-amber-100',
        textColor: 'text-amber-700',
        iconColor: 'text-amber-600',
        label: 'Confiança média',
        description: 'Confirme este valor',
      };
    case 'low':
      return {
        icon: AlertCircle,
        bgColor: 'bg-red-100',
        textColor: 'text-red-700',
        iconColor: 'text-red-600',
        label: 'Confiança baixa',
        description: 'Este valor pode estar errado',
      };
    case 'unknown':
    default:
      return {
        icon: HelpCircle,
        bgColor: 'bg-gray-100',
        textColor: 'text-gray-600',
        iconColor: 'text-gray-500',
        label: 'Desconhecida',
        description: 'Sem dados de confiança',
      };
  }
}

export function ConfidenceBadge({ 
  confidence, 
  fieldName,
  showLabel = false,
  size = 'sm'
}: ConfidenceBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  
  const level = getConfidenceLevel(confidence);
  const config = getConfidenceConfig(level);
  const Icon = config.icon;
  
  const iconSize = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';
  const badgeSize = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm';

  // Don't show badge if no confidence data
  if (level === 'unknown' && !showLabel) {
    return null;
  }

  const tooltipText = fieldName 
    ? `${fieldName}: ${config.description}${confidence !== null && confidence !== undefined ? ` (${confidence.toFixed(0)}%)` : ''}`
    : `${config.description}${confidence !== null && confidence !== undefined ? ` (${confidence.toFixed(0)}%)` : ''}`;

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        className={`
          inline-flex items-center gap-1 rounded-full font-medium
          ${config.bgColor} ${config.textColor} ${badgeSize}
          hover:opacity-80 transition-opacity cursor-help
        `}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
        aria-label={tooltipText}
      >
        <Icon className={`${iconSize} ${config.iconColor}`} />
        {showLabel && (
          <span>{confidence !== null && confidence !== undefined ? `${confidence.toFixed(0)}%` : config.label}</span>
        )}
      </button>

      {/* Tooltip */}
      {showTooltip && (
        <div 
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 
                     bg-gray-900 text-white text-xs rounded-lg shadow-lg whitespace-nowrap
                     animate-in fade-in zoom-in-95 duration-150"
          role="tooltip"
        >
          {tooltipText}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
            <div className="border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Inline confidence indicator - just the icon, for use next to form fields
 */
export function ConfidenceIndicator({ 
  confidence,
  className = ''
}: { 
  confidence: number | null | undefined;
  className?: string;
}) {
  const level = getConfidenceLevel(confidence);
  const config = getConfidenceConfig(level);
  const Icon = config.icon;

  if (level === 'unknown') return null;

  return (
    <span 
      className={`inline-flex ${config.iconColor} ${className}`}
      title={`OCR confidence: ${confidence?.toFixed(0)}%`}
    >
      <Icon className="w-4 h-4" />
    </span>
  );
}

export default ConfidenceBadge;
