import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RateLimitButtonText } from '@/components/RateLimitButtonText';
import { RATE_LIMIT_BUTTON_LABEL } from '@/lib/rateLimitCopy';
import { visibleText } from '../softDisabled';

describe('RateLimitButtonText', () => {
  it('names the button with the locked COPY-TOKENS-v1 §4a token, from content, while the seconds tick', () => {
    expect(RATE_LIMIT_BUTTON_LABEL).toBe('Tentar de novo (aguarde um momento)');
    const { rerender } = render(
      <button type="button" aria-disabled="true" className="btn-primary gap-2">
        <RateLimitButtonText seconds={45} />
      </button>,
    );
    const button = screen.getByRole('button');
    for (const seconds of [45, 44, 43]) {
      rerender(
        <button type="button" aria-disabled="true" className="btn-primary gap-2">
          <RateLimitButtonText seconds={seconds} />
        </button>,
      );
      expect(screen.getByRole('button')).toBe(button);
      expect(button).toHaveAccessibleName('Tentar de novo (aguarde um momento)');
      expect(visibleText(button)).toBe(`Tentar de novo em ${seconds} s`);
      expect(button.querySelector('[aria-label]')).toBeNull();
    }
  });

  it('renders one flex item, so a gap-* button keeps the spaces between the parts', () => {
    render(
      <button type="button" className="gap-2">
        <RateLimitButtonText seconds={3} />
      </button>,
    );
    expect(screen.getByRole('button').children).toHaveLength(1);
  });
});
