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
            <Link href="/sign-in">{t.navEntrar}</Link>
            <Link
              href={startHref}
              className="landing-btn landing-btn-primary landing-btn-sm"
            >
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
          </div>

          <FlowDiagram
            receipt={t.diagramReceipt}
            iva={t.diagramIva}
            pack={t.diagramPack}
          />

          <div id="exemplo" className="landing-example">
            <p className="landing-example-kicker">{t.exampleKicker}</p>
            <div className="landing-example-grid">
              <article className="landing-receipt" aria-label={t.receiptKicker}>
                <p className="landing-kicker">{t.receiptKicker}</p>
                <p className="landing-receipt-name">{t.receiptName}</p>
                <p className="landing-receipt-meta">{t.receiptMeta}</p>
                <p className="landing-receipt-meta">{t.receiptDate}</p>
                <hr className="landing-receipt-rule" />
                <p className="landing-receipt-row">
                  <span>{t.receiptBase}</span>
                  <span>{t.receiptBaseVal}</span>
                </p>
                <p className="landing-receipt-row">
                  <span>{t.receiptVat}</span>
                  <span>{t.receiptVatVal}</span>
                </p>
                <p className="landing-receipt-row landing-receipt-total">
                  <span>{t.receiptTotal}</span>
                  <span>{t.receiptTotalVal}</span>
                </p>
              </article>

              <article className="landing-iva" aria-label={t.ivaLabel}>
                <p className="landing-kicker">{t.ivaKicker}</p>
                <p className="landing-iva-label">{t.ivaLabel}</p>
                <p className="landing-iva-amount">{t.ivaAmount}</p>
                <p className="landing-iva-due">{t.ivaDue}</p>
                <p className="landing-iva-detail">{t.ivaDetail}</p>
              </article>

              <article className="landing-pack" aria-label={t.packKicker}>
                <p className="landing-kicker">{t.packKicker}</p>
                <p className="landing-pack-title">{t.packTitle}</p>
                <ul>
                  <li>{t.packFile1}</li>
                  <li>{t.packFile2}</li>
                  <li>{t.packFile3}</li>
                </ul>
                <p className="landing-pack-note">{t.packNote}</p>
              </article>
            </div>
            <p className="landing-example-note">{t.ivaCaveat}</p>
          </div>
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
          <Link href="/privacy">{t.footerPrivacy}</Link>
          <button type="button" onClick={toggleLang} className="landing-lang">
            {t.langLabel}
          </button>
        </div>
      </footer>
    </div>
  );
}
