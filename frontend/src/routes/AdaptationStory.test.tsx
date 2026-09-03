import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';
import { AdaptationStory } from './AdaptationStory';

describe('AdaptationStory Route & Component (P7-FE-4)', () => {
  it('renders the timeline of hedge-on to hedge-reduced with triggering events', () => {
    render(
      <MemoryRouter>
        <AdaptationStory
          initialHedgeRatio={0.80}
          finalHedgeRatio={0.30}
          initialVix={29.0}
          stabilizedVix={16.0}
        />
      </MemoryRouter>
    );

    expect(screen.getByTestId('adaptation-story')).toBeInTheDocument();
    expect(screen.getByTestId('reduction-summary')).toBeInTheDocument();

    // Summary strip checks
    expect(screen.getAllByText('80%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('30%')).toBeInTheDocument();
    expect(screen.getByText('-50%')).toBeInTheDocument();
    expect(screen.getAllByText('DECREASE').length).toBeGreaterThanOrEqual(1);

    // Timeline step assertions
    expect(screen.getByTestId('story-step-1')).toHaveTextContent(/Phase 1: Volatility Shock/i);
    expect(screen.getByTestId('story-step-1')).toHaveTextContent(/VOLATILITY_SPIKE/i);

    expect(screen.getByTestId('story-step-2')).toHaveTextContent(/Phase 2: Stabilization & Trigger Crossing/i);
    expect(screen.getByTestId('story-step-2')).toHaveTextContent(/VOLATILITY_FALL/i);

    expect(screen.getByTestId('story-step-3')).toHaveTextContent(/Phase 3: Level-2 Reassessment & Order Sizing/i);
    expect(screen.getByTestId('story-step-3')).toHaveTextContent(/DECREASE/i);
  });
});
