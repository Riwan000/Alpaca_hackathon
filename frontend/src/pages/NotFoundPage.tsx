import React from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Home } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 text-center space-y-4"
      data-testid="not-found-page"
    >
      <div className="p-3 bg-[var(--status-warning)]/10 border border-[var(--status-warning)] text-[var(--status-warning)]">
        <AlertTriangle className="w-8 h-8" />
      </div>
      <h1 className="text-3xl font-serif font-bold text-[var(--text-main)]">404 - Page Not Found</h1>
      <p className="text-xs font-mono text-[var(--text-muted)] max-w-md">
        The requested financial asset, strategy route, or terminal view could not be located on the AEGIS node.
      </p>
      <Link
        to="/"
        className="px-4 py-2 bg-[var(--brand-spruce)] text-white text-xs font-mono font-medium flex items-center gap-2 hover:bg-[#143225] transition-colors"
      >
        <Home className="w-3.5 h-3.5 text-[#A67C37]" />
        Return to Dashboard
      </Link>
    </div>
  );
};
