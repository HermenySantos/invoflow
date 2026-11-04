(function () {
  var lang = 'pt';
  var query = null;
  try {
    query = new URLSearchParams(location.search).get('lang');
  } catch (error) {
    query = null;
  }
  try {
    var stored = localStorage.getItem('invoflow_demand_lang');
    if (query === 'en' || query === 'pt') lang = query;
    else if (stored === 'en' || stored === 'pt') lang = stored;
  } catch (error) {
    if (query === 'en' || query === 'pt') lang = query;
  }
  var root = document.documentElement;
  root.lang = lang === 'en' ? 'en' : 'pt-PT';
  root.classList.toggle('lang-en', lang === 'en');
})();
