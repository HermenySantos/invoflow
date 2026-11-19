'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary component that catches JavaScript errors in child components.
 * Displays a fallback UI instead of crashing the entire app.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    
    // Log error to console (in production, send to error tracking service)
    console.error('ErrorBoundary caught an error:', error);
    console.error('Component stack:', errorInfo.componentStack);
    
    // TODO: Send to error tracking service (e.g., Sentry)
    // if (typeof window !== 'undefined' && process.env.NODE_ENV === 'production') {
    //   Sentry.captureException(error, { extra: { componentStack: errorInfo.componentStack } });
    // }
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Custom fallback UI provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      // Copy owned by the Conversion Lead (COPY-TOKENS-v1); change only with their sign-off.
      return (
        <div className="min-h-screen bg-[var(--ff-bg)] flex items-center justify-center p-4 text-[var(--ff-text)]">
          <div className="card p-6 max-w-md w-full text-center">
            <div className="w-16 h-16 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-8 h-8 text-[var(--ff-danger)]" aria-hidden="true" />
            </div>

            <h1 className="text-[20px] font-semibold mb-2">
              Algo correu mal
            </h1>

            <p className="mx-auto max-w-[36ch] text-[var(--ff-text-muted)] mb-6">
              Não conseguimos mostrar esta página. Pode tentar outra vez ou voltar aos recibos.
            </p>
            
            {/* Show error details in development */}
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <div className="mb-6 p-3 bg-gray-100 rounded-lg text-left overflow-auto max-h-40">
                <p className="text-xs font-mono text-red-600">
                  {this.state.error.message}
                </p>
                {this.state.errorInfo && (
                  <pre className="text-xs font-mono text-gray-500 mt-2 whitespace-pre-wrap">
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </div>
            )}
            
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <button
                type="button"
                onClick={this.handleRetry}
                className="btn-primary btn-md min-h-11 lg:min-h-11 gap-2"
              >
                <RefreshCw className="w-4 h-4" aria-hidden="true" />
                Tentar outra vez
              </button>

              <button
                type="button"
                onClick={this.handleReload}
                className="btn-secondary btn-md min-h-11 lg:min-h-11"
              >
                Recarregar a página
              </button>
            </div>

            {/* A client <Link> would keep this root-layout boundary in its error state; a full load resets it. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/receipts"
              className="mt-3 inline-flex min-h-11 min-w-11 items-center justify-center px-4 font-medium text-[var(--ff-accent)] underline-offset-4 hover:underline"
            >
              Ir para os recibos
            </a>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Higher-order component to wrap a component with an error boundary.
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  fallback?: ReactNode
): React.FC<P> {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}

export default ErrorBoundary;
