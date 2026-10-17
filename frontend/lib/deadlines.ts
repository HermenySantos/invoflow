// Filing dates for the periodic IVA declaration.
//
// CIVA art. 41.º n.º 1 (OCC, Essencial IVA 2026, quoting the code): the
// declaration is sent by the 20th of the second month after the period.
// Alínea a) is the monthly regime (turnover of at least €650,000). Alínea b)
// is the quarterly regime. N.º 10, renumbered by Decreto-Lei n.º 49/2025,
// sends the June monthly declaration and the second-quarter declaration by
// 20 September.
//
// A term that lands on a closed day moves to the next working day. CPPT
// art. 20.º n.º 1 (Portal das Finanças, CPPT consolidated July 2025, Lei
// n.º 7/2021) counts tax-procedure deadlines under Código Civil art. 279.º
// and transfers a term that ends on a day the tax services are closed.
// Código Civil art. 279.º alínea e) transfers a term that ends on a Sunday
// or a public holiday. Saturday is a closed day at the tax office; STA
// 8 October 2014 (processo 548/14-30) reads art. 279.º alínea e) the same way.
// Only national public holidays are treated as closed. The date below is
// the filing day (the 20th, shifted). It is not the payment day five days later.

const MONTHS_PT = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

const MONTHS_EN = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function civilDate(year: number, monthIndex: number, day: number): Date {
  return new Date(year, monthIndex, day);
}

function addDays(date: Date, days: number): Date {
  return civilDate(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function dateKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

// Anonymous Gregorian algorithm. Month is 1-based in the result.
function easterSunday(year: number): Date {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return civilDate(year, month - 1, day);
}

const holidayCache = new Map<number, Set<string>>();

function nationalHolidays(year: number): Set<string> {
  const cached = holidayCache.get(year);
  if (cached) return cached;
  const easter = easterSunday(year);
  const days = [
    civilDate(year, 0, 1),
    addDays(easter, -2),
    civilDate(year, 3, 25),
    civilDate(year, 4, 1),
    addDays(easter, 60),
    civilDate(year, 5, 10),
    civilDate(year, 7, 15),
    civilDate(year, 9, 5),
    civilDate(year, 10, 1),
    civilDate(year, 11, 1),
    civilDate(year, 11, 8),
    civilDate(year, 11, 25),
  ];
  const keys = new Set(days.map(dateKey));
  holidayCache.set(year, keys);
  return keys;
}

function isClosed(date: Date): boolean {
  const weekday = date.getDay();
  if (weekday === 0 || weekday === 6) return true;
  return nationalHolidays(date.getFullYear()).has(dateKey(date));
}

function nextWorkingDay(date: Date): Date {
  let cursor = civilDate(date.getFullYear(), date.getMonth(), date.getDate());
  while (isClosed(cursor)) {
    cursor = addDays(cursor, 1);
  }
  return cursor;
}

function statutoryFilingDate(
  periodType: 'month' | 'quarter',
  year: number,
  periodValue: number,
): Date {
  if (periodType === 'quarter') {
    // May, September, November, February. Q2 is September under art. 41.º n.º 10.
    const deadlineMonth = [4, 8, 10, 1];
    const deadlineYear = periodValue === 4 ? year + 1 : year;
    return civilDate(deadlineYear, deadlineMonth[periodValue - 1], 20);
  }
  if (periodValue === 6) {
    return civilDate(year, 8, 20);
  }
  // Second month after the period. January → March. October → December.
  const monthIndex = periodValue + 1;
  return civilDate(year + Math.floor(monthIndex / 12), monthIndex % 12, 20);
}

export function paymentDeadline(
  periodType: 'month' | 'quarter',
  year: number,
  periodValue: number,
): Date {
  return nextWorkingDay(statutoryFilingDate(periodType, year, periodValue));
}

export function formatPaymentDeadline(date: Date, lang: 'pt' | 'en'): string {
  const day = date.getDate();
  if (lang === 'pt') {
    return `Prazo de entrega: ${day} de ${MONTHS_PT[date.getMonth()]} de ${date.getFullYear()}`;
  }
  return `Filing deadline: ${day} ${MONTHS_EN[date.getMonth()]} ${date.getFullYear()}`;
}
