'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/providers/AuthProvider';
import { FlowDiagram } from './FlowDiagram';
import { LandingLang, landingCopy } from './copy';

const LANG_KEY = 'faturaflow_lang';

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const [lang, setLang] = useState<LandingLang>('pt');
  const t = landingCopy[lang];
  const startHref = isAuthenticated ? '/upload' : '/sign-in?next=/upload';

  useEffect(() => {
    const stored = window.localStorage.getItem(LANG_KEY);
    if (stored === 'en' || stored === 'pt') {
      setLang(stored);
    }
  }, []);

  const toggleLang = () => {
    const next = lang === 'pt' ? 'en' : 'pt';
    setLang(next);
    window.localStorage.setItem(LANG_KEY, next);
    document.documentElement.lang = next;
  };

  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="landing-nav-inner">
          <a href="#topo" className="landing-wordmark">
            {t.wordmark}
          </a>
          <nav className="landing-nav-links" aria-label="Secções">
            <a href="#como-funciona">{t.navComo}</a>
            <a href="#preco">{t.navPreco}</a>
            <Link href="/sign-in">{t.navEntrar}</Link>
            <Link href={startHref} className="landing-btn landing-btn-primary landing-btn-sm">
              {t.navComecar}
            </Link>
          </nav>
        </div>
      </header>

      <main id="topo">
        <section className="landing-hero">
          <h1>{t.h1}</h1>
          <p className="landing-sub">{t.sub}</p>
          <div className="landing-hero-actions">
            <Link href={startHref} className="landing-btn landing-btn-primary">
              {t.ctaPrimary}
            </Link>
            <a href="#como-funciona" className="landing-btn landing-btn-quiet">
              {t.ctaSecondary}
            </a>
          </div>
          <FlowDiagram receipt={t.diagramReceipt} iva={t.diagramIva} pack={t.diagramPack} />
        </section>

        <section id="como-funciona" className="landing-section">
          <h2>{t.howTitle}</h2>
          <ol className="landing-steps">
            <li>
              <span className="landing-step-n">1</span>
              <div>
                <strong>{t.how1Title}</strong>
                <p>{t.how1Body}</p>
              </div>
            </li>
            <li>
              <span className="landing-step-n">2</span>
              <div>
                <strong>{t.how2Title}</strong>
                <p>{t.how2Body}</p>
              </div>
            </li>
            <li>
              <span className="landing-step-n">3</span>
              <div>
                <strong>{t.how3Title}</strong>
                <p>{t.how3Body}</p>
              </div>
            </li>
          </ol>
        </section>

        <section className="landing-section">
          <h2>{t.receiveTitle}</h2>
          <ul className="landing-list">
            <li>{t.receive1}</li>
            <li>{t.receive2}</li>
            <li>{t.receive3}</li>
          </ul>
        </section>

        <section className="landing-section">
          <h2>{t.whoTitle}</h2>
          <p>{t.whoBody}</p>
        </section>

        <section className="landing-section">
          <h2>{t.trustTitle}</h2>
          <p>{t.trustBody}</p>
        </section>

        <section id="preco" className="landing-section">
          <h2>{t.priceTitle}</h2>
          <p>{t.priceBody}</p>
        </section>

        <section className="landing-cta-band">
          <h2>{t.ctaBandTitle}</h2>
          <p>{t.ctaBandBody}</p>
          <Link href={startHref} className="landing-btn landing-btn-primary">
            {t.ctaPrimary}
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <p>{t.footerNote}</p>
        <div className="landing-footer-links">
          <span>{t.footerContact}</span>
          <Link href="/privacy">{t.footerPrivacy}</Link>
          <button type="button" onClick={toggleLang} className="landing-lang">
            {t.langLabel}
          </button>
        </div>
      </footer>
    </div>
  );
}
