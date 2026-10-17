import type { LandingLang } from '@/components/landing/copy';

export type PrivacyLang = LandingLang;

type PrivacyCopy = {
  title: string;
  intro: string;
  updated: string;
  demoBanner: string;
  langLabel: string;
  controllerHeading: string;
  controllerBody: string;
  controllerName: string;
  contactLabel: string;
  dataHeading: string;
  dataIntro: string;
  dataItems: string[];
  demoBody: string;
  purposesHeading: string;
  purposes: string[];
  estimateNote: string;
  retentionHeading: string;
  retention: string[];
  processorsHeading: string;
  processorsIntro: string;
  processors: string[];
  transfersHeading: string;
  transfersBody: string;
  missingControllerDetails: string;
  rightsHeading: string;
  rightsBody: string;
  rightsItems: string[];
  rightsContact: string;
  contactHeading: string;
};

export const privacyCopy: Record<PrivacyLang, PrivacyCopy> = {
  pt: {
    title: 'Privacidade',
    intro:
      'Este aviso explica que dados pessoais o Invoflow trata, para quê, durante quanto tempo, quem os recebe e quais são os seus direitos ao abrigo do Regulamento (UE) 2016/679 (RGPD). A versão em português é a principal.',
    updated: '13 de outubro de 2026',
    demoBanner:
      'Modo de demonstração: o início de sessão e o armazenamento de ficheiros são simulados. O OCR é simulado: os valores lidos são fictícios. Os dados ficam nesta instalação.',
    langLabel: 'EN',
    controllerHeading: 'Responsável pelo tratamento',
    controllerBody: 'O responsável pelo tratamento opera o Invoflow.',
    controllerName: 'Nome: Hermenegildo Jerónimo dos Santos',
    contactLabel: 'Contacto',
    dataHeading: 'Dados tratados',
    dataIntro:
      'Tratamos o que for preciso para guardar faturas e recibos e preparar uma estimativa e um pacote de exportação:',
    dataItems: [
      'Conta: endereço de email e um identificador (da Clerk, ou, em modo de demonstração, um identificador local calculado a partir do email que escrever).',
      'Ficheiros que carrega: fotografias e PDFs de faturas e recibos.',
      'Dados lidos ou corrigidos nesses documentos, incluindo NIFs — o NIF do fornecedor e qualquer outro NIF impresso no documento, que pode identificar uma pessoa singular — bem como o nome do fornecedor, o número da fatura, a data, a base, o IVA, o total, a taxa de IVA, a categoria da despesa, notas de revisão e o texto obtido por OCR.',
      'O montante de IVA das vendas, se o escrever à mão.',
      'Preferência de idioma e, em modo de demonstração, o email guardado no armazenamento local do browser.',
      'Dados técnicos mínimos para o serviço responder. Se o Sentry estiver configurado, relatórios de erro sem dados pessoais por omissão.',
    ],
    demoBody:
      'Em modo de demonstração não é pedida palavra-passe e os ficheiros ficam no armazenamento local dessa instalação. Clerk, Cloudflare R2 e Sentry só recebem dados quando estão configurados.',
    purposesHeading: 'Finalidades e base legal',
    purposes: [
      'Prestar o serviço pedido: guardar recibos, mostrar uma estimativa de IVA e gerar um pacote de exportação. Base: execução de contrato ou diligências pré-contratuais (artigo 6.º, n.º 1, alínea b), do RGPD).',
      'Manter a conta e separar os seus documentos dos de outras pessoas. Base: artigo 6.º, n.º 1, alínea b).',
      'Conservar os ficheiros originais depois de ocultar um recibo na aplicação, porque o produto não os apaga. Base: artigo 6.º, n.º 1, alínea b) e, quando exista um dever legal de conservação que se aplique, alínea c).',
      'Diagnosticar falhas e proteger o serviço, se o Sentry estiver ligado. Base: interesse legítimo num serviço fiável e seguro (artigo 6.º, n.º 1, alínea f)). Não usamos estes dados para publicidade e não os vendemos.',
    ],
    estimateNote:
      'A estimativa de IVA é um número para rever. O Invoflow não envia declarações à Autoridade Tributária.',
    retentionHeading: 'Conservação',
    retention: [
      'Ficheiros originais, dados extraídos (incluindo NIFs) e o registo associado: ocultar um recibo não os apaga. O produto conserva-os durante 10 anos.',
      'Numa instalação de produção, as cópias de segurança da base de dados ficam cerca de 30 dias.',
      'Email e identificador da conta: enquanto a conta existir. Pode pedir o apagamento. A parte que ainda tenha de ser conservada com a fatura pode permanecer, separada do email quando isso for possível.',
      'Relatórios do Sentry, se existirem: segundo a configuração desse projeto. Por omissão não enviamos dados pessoais.',
      'Modo de demonstração: os dados ficam na máquina dessa instalação até alguém apagar a base de dados local e a pasta de armazenamento.',
    ],
    processorsHeading: 'Subcontratantes na instalação na UE',
    processorsIntro:
      'Quando o serviço corre na instalação de produção na União Europeia, estes subcontratantes tratam dados por conta do responsável:',
    processors: [
      'Hetzner — alojamento da aplicação e da base de dados (UE: Alemanha ou Finlândia).',
      'Cloudflare R2 — ficheiros dos recibos e cópias de segurança.',
      'Clerk — autenticação, quando o modo de demonstração está desligado.',
      'Sentry — relatórios de erro, opcional.',
    ],
    transfersHeading: 'Transferências internacionais',
    transfersBody:
      'Clerk (autenticação), Sentry (relatórios de erro) e Cloudflare (ficheiros e rede) são empresas estabelecidas nos Estados Unidos. Quando os dados são tratados por esses destinatários, os instrumentos previstos são as cláusulas contratuais-tipo adotadas pela Comissão Europeia e, se o destinatário estiver certificado, o Quadro de Privacidade de Dados UE-EUA (EU-US Data Privacy Framework).',
    missingControllerDetails: 'Morada e NIF disponibilizados mediante pedido',
    rightsHeading: 'Direitos',
    rightsBody:
      'Pode pedir acesso, retificação, apagamento, limitação e portabilidade dos seus dados pessoais, e opor-se ao tratamento baseado em interesse legítimo. Pode apresentar reclamação à Comissão Nacional de Proteção de Dados (cnpd.pt).',
    rightsItems: [
      'Acesso aos dados que tratamos sobre si.',
      'Retificação de dados inexatos.',
      'Apagamento, com o limite da conservação das faturas descrita acima.',
      'Limitação do tratamento e portabilidade dos dados que nos forneceu.',
      'Oposição ao tratamento assente em interesse legítimo.',
    ],
    rightsContact: 'Para exercer estes direitos, escreva para o contacto abaixo.',
    contactHeading: 'Contacto',
  },
  en: {
    title: 'Privacy',
    intro:
      'This notice explains what personal data Invoflow processes, why, for how long, who receives it, and your rights under Regulation (EU) 2016/679 (GDPR). The Portuguese version is the main one.',
    updated: '13 October 2026',
    demoBanner:
      'Demo mode: sign-in and file storage are mock. OCR is mock: the values it reads are invented. Data stays on this installation.',
    langLabel: 'PT',
    controllerHeading: 'Data controller',
    controllerBody: 'The controller operates Invoflow.',
    controllerName: 'Name: Hermenegildo Jerónimo dos Santos',
    contactLabel: 'Contact',
    dataHeading: 'Data we process',
    dataIntro:
      'We process what is needed to keep invoices and receipts and to prepare an estimate and an export pack:',
    dataItems: [
      'Account: email address and an identifier (from Clerk, or, in demo mode, a local identifier derived from the email you type).',
      'Files you upload: photos and PDFs of invoices and receipts.',
      'Data read from or corrected on those documents, including NIFs — the supplier NIF and any other NIF printed on the document, which may identify a natural person — plus supplier name, invoice number, date, net, VAT, gross, VAT rate, expense category, review notes, and the OCR text.',
      'The VAT-on-sales amount, if you type it in.',
      'Language preference and, in demo mode, the email stored in the browser’s local storage.',
      'The minimum technical data needed to answer requests. If Sentry is configured, error reports without personal data by default.',
    ],
    demoBody:
      'In demo mode no password is checked and files stay on that installation’s local storage. Clerk, Cloudflare R2, and Sentry receive data only when they are configured.',
    purposesHeading: 'Purposes and legal basis',
    purposes: [
      'Provide the service you asked for: store receipts, show an IVA estimate, and build an export pack. Basis: contract, or steps before a contract (GDPR Article 6(1)(b)).',
      'Keep the account and separate your documents from other people’s. Basis: Article 6(1)(b).',
      'Keep original files after you hide a receipt in the app, because the product does not erase them. Basis: Article 6(1)(b) and, where a legal duty to keep them applies, Article 6(1)(c).',
      'Diagnose failures and protect the service, if Sentry is on. Basis: legitimate interest in a reliable, secure service (Article 6(1)(f)). We do not use this data for advertising and we do not sell it.',
    ],
    estimateNote:
      'The IVA figure is an estimate to review. Invoflow does not file returns with the tax authority.',
    retentionHeading: 'Retention',
    retention: [
      'Original files, extracted data (including NIFs), and the related record: hiding a receipt does not delete them. The product keeps them for 10 years.',
      'On a production installation, database backups are kept for about 30 days.',
      'Email and account identifier: for as long as the account exists. You can ask for erasure. The part that still has to be kept with the invoice may remain, separated from the email where that is possible.',
      'Sentry reports, if any: according to that project’s settings. Personal data is not sent by default.',
      'Demo mode: data stays on that installation’s machine until someone deletes the local database and the storage folder.',
    ],
    processorsHeading: 'Processors for the EU installation',
    processorsIntro:
      'When the service runs on the production installation in the European Union, these processors handle data for the controller:',
    processors: [
      'Hetzner — hosting of the application and the database (EU: Germany or Finland).',
      'Cloudflare R2 — receipt files and backups.',
      'Clerk — authentication, when demo mode is off.',
      'Sentry — error reports, optional.',
    ],
    transfersHeading: 'International transfers',
    transfersBody:
      'Clerk (authentication), Sentry (error reports) and Cloudflare (files and network) are companies established in the United States. Where those recipients process data, the instruments provided for are the European Commission’s standard contractual clauses and, if the recipient is certified, the EU-US Data Privacy Framework.',
    missingControllerDetails: 'Address and NIF are available on request',
    rightsHeading: 'Your rights',
    rightsBody:
      'You can ask for access, rectification, erasure, restriction, and portability of your personal data, and object to processing based on legitimate interests. You can lodge a complaint with the Portuguese data protection authority, CNPD (cnpd.pt).',
    rightsItems: [
      'Access to the personal data we process about you.',
      'Rectification of inaccurate data.',
      'Erasure, limited by the invoice retention described above.',
      'Restriction of processing and portability of the data you provided.',
      'Objection to processing based on legitimate interests.',
    ],
    rightsContact: 'To use these rights, email the contact below.',
    contactHeading: 'Contact',
  },
};
