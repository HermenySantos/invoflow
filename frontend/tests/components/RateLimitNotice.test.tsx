import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RateLimitNotice } from '@/components/RateLimitNotice';
import { expectEmptyRegion, expectRegionSays, getRateLimitRegion } from '../rateLimitRegion';

const MESSAGE = 'Aguarde um momento. Pode tentar de novo dentro de 30 s.';

describe('RateLimitNotice live region', () => {
  it('renders an empty, mounted status region when there is no message', () => {
    render(<RateLimitNotice message={null} />);
    expectEmptyRegion(getRateLimitRegion());
    expect(screen.queryByTestId('rate-limit-notice')).not.toBeInTheDocument();
  });

  it('puts the message into the same region node, then empties it again, without remounting', () => {
    const { rerender } = render(<RateLimitNotice message={null} className="mt-3" />);
    const region = getRateLimitRegion();

    rerender(<RateLimitNotice message={MESSAGE} className="mt-3" />);
    expect(getRateLimitRegion()).toBe(region);
    expectRegionSays(region, MESSAGE);
    // The visible box is inside the region; spacing goes on the box, so the empty region takes no room.
    const box = screen.getByTestId('rate-limit-notice');
    expect(region).toContainElement(box);
    expect(box).not.toHaveAttribute('role');
    expect(box).toHaveClass('mt-3');
    expect(region).not.toHaveClass('mt-3');

    rerender(<RateLimitNotice message={null} className="mt-3" />);
    expect(getRateLimitRegion()).toBe(region);
    expectEmptyRegion(region);
  });

  it('drops any parent space-y margin while empty (jsdom has no layout; real-browser heights checked in the PR)', () => {
    render(<RateLimitNotice message={null} />);
    expect(getRateLimitRegion()).toHaveClass('empty:!my-0');
  });
});
