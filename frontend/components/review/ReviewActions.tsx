'use client';

import React from 'react';
import { 
  CheckCircle, 
  Save, 
  Loader2,
  UserCheck,
  RefreshCw
} from 'lucide-react';

type ReviewStatus = 'ready' | 'needs_review' | 'accountant_review' | 'failed';

interface ReviewActionsProps {
  currentStatus: string;
  isSaving: boolean;
  onSave: (newStatus?: ReviewStatus) => void;
  onRequestRescan?: () => void;
  hasChanges?: boolean;
}

export function ReviewActions({
  currentStatus,
  isSaving,
  onSave,
  onRequestRescan,
  hasChanges = false,
}: ReviewActionsProps) {
  const isNeedsReview = currentStatus === 'needs_review';
  const isAccountantReview = currentStatus === 'accountant_review';
  const isReady = currentStatus === 'ready';

  return (
    <div className="space-y-3">
      {/* Primary action */}
      {isNeedsReview || isAccountantReview ? (
        <button
          onClick={() => onSave('ready')}
          disabled={isSaving}
          className="btn-primary btn-lg w-full flex items-center justify-center gap-2"
        >
          {isSaving ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <CheckCircle className="w-5 h-5" />
              Mark as Reviewed
            </>
          )}
        </button>
      ) : (
        <button
          onClick={() => onSave()}
          disabled={isSaving || !hasChanges}
          className="btn-primary btn-lg w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-5 h-5" />
              Save Changes
            </>
          )}
        </button>
      )}

      {/* Secondary actions */}
      <div className="flex gap-2">
        {/* Send to accountant (only show if not already in that status) */}
        {!isAccountantReview && !isReady && (
          <button
            onClick={() => onSave('accountant_review')}
            disabled={isSaving}
            className="flex-1 btn-secondary btn-md flex items-center justify-center gap-2"
          >
            <UserCheck className="w-4 h-4" />
            <span className="hidden sm:inline">Send to</span> Accountant
          </button>
        )}

        {/* Request rescan (for failed or problematic documents) */}
        {onRequestRescan && (
          <button
            onClick={onRequestRescan}
            disabled={isSaving}
            className="flex-1 btn-secondary btn-md flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Re-scan
          </button>
        )}
      </div>

      {/* Status info */}
      {isReady && !hasChanges && (
        <p className="text-center text-sm text-gray-500">
          This document has been reviewed and is ready for export.
        </p>
      )}
    </div>
  );
}

export default ReviewActions;
