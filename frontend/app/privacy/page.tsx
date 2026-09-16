import Link from 'next/link';

export default function PrivacyPage() {
  return (
    <div className="landing">
      <main className="landing-section" style={{ paddingTop: '3rem' }}>
        <p>
          <Link href="/">← FaturaFlow</Link>
        </p>
        <h1>Privacidade</h1>
        <p>
          Texto legal ainda não está publicado. Em modo de demonstração, os ficheiros ficam no
          armazenamento local desta instalação e a autenticação é simulada.
        </p>
        <p>
          Privacy copy is not published yet. In demo mode, files stay on this installation’s local
          storage and sign-in is mocked.
        </p>
      </main>
    </div>
  );
}
