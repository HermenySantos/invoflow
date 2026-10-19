const KEY = 'invoflow_demand_lang';

const text = {
  pt: {
    title: 'Página não encontrada',
    body: 'Este endereço não existe.',
    home: 'Voltar ao início',
    skip: 'Saltar para o conteúdo',
    toggle: 'EN',
  },
  en: {
    title: 'Page not found',
    body: 'This address does not exist.',
    home: 'Back to the start',
    skip: 'Skip to content',
    toggle: 'PT',
  },
};

let lang = 'pt';

try {
  const stored = localStorage.getItem(KEY);
  if (stored === 'en' || stored === 'pt') lang = stored;
} catch (error) {
  if (!(error instanceof DOMException)) throw error;
}

function apply() {
  const copy = text[lang];
  document.documentElement.lang = lang === 'en' ? 'en' : 'pt-PT';
  document.documentElement.classList.toggle('lang-en', lang === 'en');
  document.title = copy.title;
}

document.querySelector('#lang-toggle').addEventListener('click', () => {
  lang = lang === 'pt' ? 'en' : 'pt';
  try {
    localStorage.setItem(KEY, lang);
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
  }
  apply();
});

apply();
