import type { Mock } from 'vitest';

type ParamsMock = Mock<[], { id: string }>;

let registered: ParamsMock | undefined;

export function registerUseParamsMock(mock: ParamsMock) {
  registered = mock;
}

export function getUseParamsMock(): ParamsMock {
  if (!registered) {
    throw new Error('useParams mock was not registered');
  }
  return registered;
}
