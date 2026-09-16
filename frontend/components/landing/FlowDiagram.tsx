type FlowDiagramProps = {
  receipt: string;
  iva: string;
  pack: string;
};

export function FlowDiagram({ receipt, iva, pack }: FlowDiagramProps) {
  return (
    <svg
      className="landing-diagram"
      viewBox="0 0 560 92"
      role="img"
      aria-label={`${receipt} → ${iva} → ${pack}`}
    >
      <rect x="8" y="18" width="140" height="56" rx="6" fill="#FFFFFF" stroke="#E5E5E0" />
      <text x="78" y="52" textAnchor="middle" fill="#1A1A1A" fontSize="14">
        {receipt}
      </text>

      <path d="M156 46 H208" stroke="#1B4D3E" strokeWidth="1.5" fill="none" />
      <path d="M200 40 L208 46 L200 52" stroke="#1B4D3E" strokeWidth="1.5" fill="none" />

      <rect x="212" y="18" width="140" height="56" rx="6" fill="#FFFFFF" stroke="#E5E5E0" />
      <text x="282" y="52" textAnchor="middle" fill="#1A1A1A" fontSize="14">
        {iva}
      </text>

      <path d="M360 46 H412" stroke="#1B4D3E" strokeWidth="1.5" fill="none" />
      <path d="M404 40 L412 46 L404 52" stroke="#1B4D3E" strokeWidth="1.5" fill="none" />

      <rect x="416" y="18" width="140" height="56" rx="6" fill="#FFFFFF" stroke="#1B4D3E" />
      <text x="486" y="52" textAnchor="middle" fill="#1B4D3E" fontSize="14">
        {pack}
      </text>
    </svg>
  );
}
