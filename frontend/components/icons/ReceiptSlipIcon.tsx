/** A blank till slip with a perforated tear edge; carries no currency glyph. */
export function ReceiptSlipIcon({ className }: { className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      data-icon="receipt-slip"
    >
      <path d="M5 3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v18l-2.33-1.5L14.33 21 12 19.5 9.67 21l-2.34-1.5L5 21Z" />
      <path d="M5 6h14" strokeDasharray="1 2.5" />
      <path d="M9 10h6" />
      <path d="M9 14h4" />
    </svg>
  );
}
