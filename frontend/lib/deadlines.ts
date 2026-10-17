export function paymentDeadline(
  periodType: 'month' | 'quarter',
  year: number,
  periodValue: number,
): Date {
  if (periodType === 'quarter') {
    const deadlineMonth = [4, 8, 10, 1];
    const deadlineYear = periodValue === 4 ? year + 1 : year;
    return new Date(deadlineYear, deadlineMonth[periodValue - 1], 20);
  }
  const deadlineYear = periodValue === 12 ? year + 1 : year;
  const monthIdx = periodValue === 12 ? 0 : periodValue;
  return new Date(deadlineYear, monthIdx, 20);
}

const MONTHS_PT = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

const MONTHS_EN = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export function formatPaymentDeadline(date: Date, lang: 'pt' | 'en'): string {
  const day = date.getDate();
  if (lang === 'pt') {
    return `Prazo ${day} de ${MONTHS_PT[date.getMonth()]} de ${date.getFullYear()}`;
  }
  return `Due ${day} ${MONTHS_EN[date.getMonth()]} ${date.getFullYear()}`;
}
