'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LANG_KEY, LandingLang } from '@/components/landing/copy';
import { isDemoMode } from '@/lib/demoUser';
import { privacyCopy } from './copy';

const CONTACT_EMAIL = 'hermeny7@hotmail.com';

function Todo({ children }: { children: string }) {
  return (
    <li>
      <span className="landing-todo">TODO</span>
      {children}
    </li>
  );
}

export function PrivacyPage() {
  const [lang, setLang] = useState<LandingLang>('pt');
  const t = privacyCopy[lang];

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
          <Link href="/" className="landing-wordmark">
            Invoflow
          </Link>
          <button type="button" onClick={toggleLang} className="landing-lang">
            {t.langLabel}
          </button>
        </div>
      </header>

      <main className="landing-prose">
        <h1>{t.title}</h1>
        <p className="landing-sub">{t.intro}</p>
        <p className="landing-example-note">{t.updated}</p>

        {isDemoMode ? <p className="landing-pilot-note">{t.demoBanner}</p> : null}

        <h2>{t.controllerHeading}</h2>
        <p>{t.controllerBody}</p>
        <ul>
          <Todo>{t.controllerName}</Todo>
          <Todo>{t.controllerAddress}</Todo>
          <Todo>{t.controllerNif}</Todo>
        </ul>
        <p>
          {t.contactLabel}:{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{' '}
          <span className="landing-confirm">({t.contactNote})</span>
        </p>

        <h2>{t.dataHeading}</h2>
        <p>{t.dataIntro}</p>
        <ul>
          {t.dataItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p>{t.demoBody}</p>

        <h2>{t.purposesHeading}</h2>
        <ul>
          {t.purposes.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p>{t.estimateNote}</p>

        <h2>{t.retentionHeading}</h2>
        <ul>
          {t.retention.map((item) => (
            <li key={item}>{item}</li>
          ))}
          <Todo>{t.retentionTodo}</Todo>
        </ul>

        <h2>{t.processorsHeading}</h2>
        <p>{t.processorsIntro}</p>
        <ul>
          {t.processors.map((item) => (
            <li key={item}>{item}</li>
          ))}
          <Todo>{t.processorsTodo}</Todo>
        </ul>

        <h2>{t.rightsHeading}</h2>
        <p>{t.rightsBody}</p>
        <ul>
          {t.rightsItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p>{t.rightsContact}</p>

        <h2>{t.contactHeading}</h2>
        <p>
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{' '}
          <span className="landing-confirm">({t.contactNote})</span>
        </p>
      </main>
    </div>
  );
}
