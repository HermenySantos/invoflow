/**
 * Category constants, labels, colors, and icon names for expense/IRS categorization.
 */

export interface CategoryInfo {
  key: string;
  label: string;
  /** Lucide icon name */
  icon: string;
  /** Tailwind bg color class */
  color: string;
  /** Tailwind text color class */
  textColor: string;
  /** IVA deductible percentage (0-100) */
  deductiblePct: number;
}

// ── Business Expense Categories ──

export const EXPENSE_CATEGORIES: Record<string, CategoryInfo> = {
  food: {
    key: 'food',
    label: 'Alimentação',
    icon: 'UtensilsCrossed',
    color: 'bg-orange-100',
    textColor: 'text-orange-700',
    deductiblePct: 0,  // Art. 21(1)(d) CIVA: food, beverages, meals excluded
  },
  travel: {
    key: 'travel',
    label: 'Transporte',
    icon: 'Car',
    color: 'bg-blue-100',
    textColor: 'text-blue-700',
    deductiblePct: 0,  // Art. 21(1)(c) CIVA: transport & business travel excluded
  },
  utilities: {
    key: 'utilities',
    label: 'Serviços',
    icon: 'Zap',
    color: 'bg-yellow-100',
    textColor: 'text-yellow-700',
    deductiblePct: 100,
  },
  fuel: {
    key: 'fuel',
    label: 'Combustível',
    icon: 'Fuel',
    color: 'bg-red-100',
    textColor: 'text-red-700',
    deductiblePct: 50,
  },
  health: {
    key: 'health',
    label: 'Saúde',
    icon: 'Heart',
    color: 'bg-pink-100',
    textColor: 'text-pink-700',
    deductiblePct: 0,
  },
  education: {
    key: 'education',
    label: 'Educação',
    icon: 'GraduationCap',
    color: 'bg-indigo-100',
    textColor: 'text-indigo-700',
    deductiblePct: 0,
  },
  housing: {
    key: 'housing',
    label: 'Habitação',
    icon: 'Home',
    color: 'bg-emerald-100',
    textColor: 'text-emerald-700',
    deductiblePct: 0,
  },
  office: {
    key: 'office',
    label: 'Escritório',
    icon: 'Briefcase',
    color: 'bg-slate-100',
    textColor: 'text-slate-700',
    deductiblePct: 100,
  },
  marketing: {
    key: 'marketing',
    label: 'Publicidade',
    icon: 'Megaphone',
    color: 'bg-purple-100',
    textColor: 'text-purple-700',
    deductiblePct: 100,
  },
  services: {
    key: 'services',
    label: 'Serviços Prof.',
    icon: 'Wrench',
    color: 'bg-cyan-100',
    textColor: 'text-cyan-700',
    deductiblePct: 100,
  },
  equipment: {
    key: 'equipment',
    label: 'Equipamento',
    icon: 'Monitor',
    color: 'bg-teal-100',
    textColor: 'text-teal-700',
    deductiblePct: 100,
  },
  other: {
    key: 'other',
    label: 'Outro',
    icon: 'Tag',
    color: 'bg-gray-100',
    textColor: 'text-gray-600',
    deductiblePct: 0,
  },
};

// ── IRS Deduction Sectors ──

export const IRS_SECTORS: Record<string, CategoryInfo> = {
  saude: {
    key: 'saude',
    label: 'Saúde',
    icon: 'Heart',
    color: 'bg-pink-100',
    textColor: 'text-pink-700',
    deductiblePct: 0,
  },
  educacao: {
    key: 'educacao',
    label: 'Educação',
    icon: 'GraduationCap',
    color: 'bg-indigo-100',
    textColor: 'text-indigo-700',
    deductiblePct: 0,
  },
  habitacao: {
    key: 'habitacao',
    label: 'Habitação',
    icon: 'Home',
    color: 'bg-emerald-100',
    textColor: 'text-emerald-700',
    deductiblePct: 0,
  },
  lares: {
    key: 'lares',
    label: 'Lares',
    icon: 'Users',
    color: 'bg-amber-100',
    textColor: 'text-amber-700',
    deductiblePct: 0,
  },
  reparacao_automoveis: {
    key: 'reparacao_automoveis',
    label: 'Rep. Automóveis',
    icon: 'Wrench',
    color: 'bg-cyan-100',
    textColor: 'text-cyan-700',
    deductiblePct: 0,
  },
  reparacao_motos: {
    key: 'reparacao_motos',
    label: 'Rep. Motociclos',
    icon: 'Wrench',
    color: 'bg-cyan-100',
    textColor: 'text-cyan-700',
    deductiblePct: 0,
  },
  restauracao_alojamento: {
    key: 'restauracao_alojamento',
    label: 'Restauração',
    icon: 'UtensilsCrossed',
    color: 'bg-orange-100',
    textColor: 'text-orange-700',
    deductiblePct: 0,
  },
  cabeleireiros: {
    key: 'cabeleireiros',
    label: 'Cabeleireiros',
    icon: 'Scissors',
    color: 'bg-violet-100',
    textColor: 'text-violet-700',
    deductiblePct: 0,
  },
  veterinarios: {
    key: 'veterinarios',
    label: 'Veterinários',
    icon: 'Heart',
    color: 'bg-lime-100',
    textColor: 'text-lime-700',
    deductiblePct: 0,
  },
  ginasios: {
    key: 'ginasios',
    label: 'Ginásios',
    icon: 'Dumbbell',
    color: 'bg-sky-100',
    textColor: 'text-sky-700',
    deductiblePct: 0,
  },
  geral: {
    key: 'geral',
    label: 'Despesas Gerais',
    icon: 'Tag',
    color: 'bg-gray-100',
    textColor: 'text-gray-600',
    deductiblePct: 0,
  },
  isento: {
    key: 'isento',
    label: 'Isento',
    icon: 'Ban',
    color: 'bg-gray-50',
    textColor: 'text-gray-400',
    deductiblePct: 0,
  },
};

/**
 * Get category info by key, with fallback.
 */
export function getExpenseCategoryInfo(key: string | null | undefined): CategoryInfo {
  return EXPENSE_CATEGORIES[key || 'other'] || EXPENSE_CATEGORIES.other;
}

export function getIrsSectorInfo(key: string | null | undefined): CategoryInfo {
  return IRS_SECTORS[key || 'geral'] || IRS_SECTORS.geral;
}

/**
 * Ordered list for filter/picker UIs.
 */
export const EXPENSE_CATEGORY_LIST: CategoryInfo[] = Object.values(EXPENSE_CATEGORIES);
export const IRS_SECTOR_LIST: CategoryInfo[] = Object.values(IRS_SECTORS);
