'use client';

import { useId, useState } from 'react';
import { clsx } from 'clsx';
import {
  PT_DATE_INVALID,
  PT_DATE_PLACEHOLDER,
  formatPtDate,
  maskPtDate,
  parsePtDate,
} from '@/lib/ptDate';

export const PT_DATE_AFTER_MAX = 'A data não pode ser posterior a hoje.';

interface PtDateInputProps {
  id?: string;
  label: string;
  /** ISO yyyy-mm-dd, or '' when empty. */
  value: string;
  /** Called on blur with ISO yyyy-mm-dd or ''. Never called with text that is not a real date. */
  onChange: (iso: string) => void;
  onValidityChange?: (valid: boolean) => void;
  /** Latest allowed ISO date. */
  max?: string;
  className?: string;
  labelClassName?: string;
  inputClassName?: string;
}

/**
 * A text date field that always reads dd/mm/aaaa. Native type="date" follows the
 * browser locale and can show mm/dd/yyyy, so it is not used here.
 */
export function PtDateInput({
  id: idProp,
  label,
  value,
  onChange,
  onValidityChange,
  max,
  className,
  labelClassName,
  inputClassName,
}: PtDateInputProps) {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const helperId = `${id}-helper`;
  const errorId = `${id}-error`;
  const [text, setText] = useState(() => formatPtDate(value));
  const [error, setError] = useState<string | null>(null);
  const [trackedValue, setTrackedValue] = useState(value);

  // The parent can reset the value (e.g. "Limpar filtros"); show what it holds.
  if (trackedValue !== value) {
    setTrackedValue(value);
    if (parsePtDate(text) !== value) {
      setText(formatPtDate(value));
      setError(null);
    }
  }

  const handleBlur = () => {
    const iso = parsePtDate(text);
    const message =
      iso === null ? PT_DATE_INVALID : max && iso && iso > max ? PT_DATE_AFTER_MAX : null;
    setError(message);
    onValidityChange?.(message === null);
    if (message !== null || iso === null) return;
    setText(formatPtDate(iso));
    if (iso !== value) onChange(iso);
  };

  return (
    <div className={className}>
      <label htmlFor={id} className={labelClassName}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={PT_DATE_PLACEHOLDER}
        maxLength={10}
        value={text}
        onChange={(e) => {
          setText(maskPtDate(e.target.value));
          if (error) setError(null);
        }}
        onBlur={handleBlur}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? errorId : helperId}
        className={clsx(
          inputClassName,
          error && 'border-[color:var(--ff-danger)] focus:border-[color:var(--ff-danger)]',
        )}
      />
      {error ? (
        <p id={errorId} className="mt-1 text-sm text-[color:var(--ff-danger)]">
          {error}
        </p>
      ) : (
        <p id={helperId} className="mt-1 text-xs text-[#5c5c5c]">
          {PT_DATE_PLACEHOLDER}
        </p>
      )}
    </div>
  );
}
