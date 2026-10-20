# Invoflow landing page: COPY v4 (interest list), PT-PT + EN

- **Status:** DRAFT for Invoflow Operator (words) and Gildo (anything public). Nothing here is public, sent or shipped.
- **Author:** Conversion Lead (words and message order). **Positioning, ICP, claims:** CVO (locked 2026-10-17). **Product facts:** Invoflow Operator (COPY-v2-factcheck.md, main `35e20ef`).
- **Date:** 2026-10-17, ~21:40 Lisbon (UTC+1). **Deadline:** Sun 18 Oct 2026, 12:00 Lisbon.
- **Brief:** `/workspace/conversion-copy/requests/invoflow-landing-v1.md` (authoritative).
- **Baseline:** `COPY-v3.md` (CVO), left unchanged. v4 supersedes it for the build.
- **Target:** PR #27 `site/` (`js/copy.js`, `index.html`), via Invoflow Operator's coding agent. Crazy QA gates. Gildo says go.
- **Side files (same folder):** `COPY-v4-claims.md` (claim → source), `COPY-v4-for-gildo.md` (decisions, owners), `COPY-v4-hierarchy.md` (message hierarchy, ad-hook tests), `COPY-v4-emails.md` (confirm, welcome and nurture drafts).

> **Rules for whoever implements this copy**
> - Text in `[square brackets]` is an open token. **Never ship a bracket.** Replace it after the owner decides, or cut the sentence. Links are written as `«link text» → /path` and are not tokens.
> - **PT-PT and EN strings are separate keys.** Never mix them in one string.
> - `site/check.mjs` bans on the visible page (found at `invoflow-gate-pr27/src/site/check.mjs:17-27`): "accountant-ready", "pronto para o contabilista", "a pagar", "café/cafe", "restaurante", "TODO", "a confirmar", "prazo", and written dates like "20 de maio". Use **"a entregar"**, never "a pagar". This copy also avoids "calcula" (CVO ban) and "IVA dedutível" as a promise.
> - Every IVA figure or result carries **estimativa / estimate**.
> - **No price, no discount and no pilot offer anywhere on the page** (Gildo, 17 Oct). No `€` next to a digit anywhere.
> - **Fictional figures:** only the hero sheet set approved by Gildo (2026-10-17 21:41, this case only). No other fictional numbers anywhere.
> - Static page, CSP `'self'`: no copy here depends on embeds, external fonts, widgets or third-party scripts.

---

## Changelog v3 → v4 (summary; detail per item in `COPY-v4-for-gildo.md` where a decision is still open)

| # | v3 | v4 | Why |
|---|---|---|---|
| 1 | Hero price hint "Pack IVA: €190/trimestre. Piloto: primeiro trimestre com desconto." / "Pack IVA: €190 per quarter. Pilot: first quarter discounted." | **Removed.** Replaced by a friction line under the CTA: "Só pedimos o email. Sem compromisso." | Gildo 17 Oct: no price, no pilot offer on the page. Conflicts with DESIGN-SPEC §12.3 (UI Lead to update). |
| 2 | §5 Pilot: price block "**Pack IVA: €190/trimestre.** Piloto: primeiro trimestre com desconto de [desconto: € ou %]." / EN equivalent | **Removed with the whole pilot offer.** | Same. The parent's earlier "keep any lower-page price block and flag it" is superseded by the brief: no price anywhere. |
| 3 | §5 Pilot "O que recebe" (access for a quarter, founder contact via [canal de suporte]) and "O que lhe pedimos" (real quarter, [formato do feedback], show the pack) | **Removed.** "O que recebe / What you get" now describes what joining the list gives (in §7). | No pilot offer on the page. Keeps check.mjs' required "O que recebe" / "What you get" strings honest. |
| 4 | §5 Pilot "Limites, com honestidade" inside the offer band | **Promoted to its own section §5 "Limites, com honestidade"**, the one deliberate place for limits. | "Honest limits said once, in a deliberate place." The hero caveat line is dropped (see 6). |
| 5 | CTA / form title / submit "Reservar lugar no piloto" / "Reserve a pilot place"; header "Reservar" | **"Avisem-me" / "Keep me posted"** in the hero, the header and the form submit (end of page). Form title "Quer saber quando a Invoflow abrir?" | Interest list, low commitment (brief). One primary CTA per view. |
| 6 | Hero caveat line "É uma estimativa, não um cálculo oficial. Não substitui o contabilista e nada é enviado às Finanças." | **Dropped from the hero.** The hero sub keeps "estimativa"; all limits live in §5. | Limits once. Also removes "cálculo" (CVO bans "calcula"). **Flagged** in for-gildo #4: CVO may want a one-line caveat back near the H1. |
| 7 | Form: name, email, 3 qualifier radios (regime, faturas por mês, contabilista), consent. Intro "São seis perguntas rápidas…" / "Six quick questions…" | **Email + one required, unticked consent tick. Nothing else.** The "seis perguntas" bug is gone with the intro. | Gildo 17 Oct. Backend impact (`qualify.js` `parseAnswers()` rejects a body without name and the 3 answers) flagged to Invoflow Operator. |
| 8 | Thank-you "Obrigado, recebemos o seu pedido. Vamos ver se o piloto encaixa no seu caso e respondemos por email em [dias até à resposta]." | **"Obrigado. Está na lista."** No reply time, no qualification. Two variants (with or without double opt-in). | Brief: the form must not promise a reply time. |
| 9 | (none) duplicate email state | **Duplicate email shows exactly the success state** (same words, same element, same focus). | GATE-93fcead P1-2 enumeration oracle; the words must not leak membership either. |
| 10 | FAQ 7 "Quanto custa? O Pack IVA custa €190 por trimestre. No piloto, o primeiro trimestre tem desconto. Esta página não cobra nada." | **Rewritten without price or discount:** "Ainda não há preço público. Quando houver, quem está na lista sabe por email. Deixar o email não o compromete a nada, e esta página não cobra nada." | No price on the page. Original kept here. CVO may prefer to cut FAQ 7 entirely (for-gildo #7). |
| 11 | Ad hook 3 "Saiba uma estimativa do seu IVA antes do fim do trimestre. Piloto para ENI e microempresas: 1.º trimestre com desconto." | **"Saiba uma estimativa do seu IVA antes do fim do trimestre. Para ENI e microempresas. Deixe o email e avisamos."** | No discount. Original kept here. Hooks now 5 (top 3 marked for CVO's Meta test). |
| 12 | Hero ledger figures (DESIGN-SPEC §3: 41,86 / 230,00 / 188,14, vendor names, period "T4 · 2026") | **Replaced by a visible token** `[figuras do exemplo — aguarda aprovação do Gildo]`. Labels kept (reworded), figures not. | Hard rule: no fictional figures without Gildo approving the specific case. Top item in for-gildo. **Superseded by 4.1-8 (Gildo approved the set).** |
| 13 | "IVA dedutível" (step 3, pilot, FAQ 2; sheet row "IVA dedutível (compras)") | **"o IVA das suas faturas de despesas"**; sheet row "IVA das faturas de despesas". | Brief/CVO: no "IVA dedutível" as a promise. Accuracy nuance flagged (the app subtracts only the deductible share). |
| 14 | FAQ 5 "Nos PDF, a Invoflow lê o texto da fatura." | **Cut.** "Sim. Pode carregar o PDF tal como chegou, ou uma fotografia." | CVO: don't mention PDF QR at all; the PDF read path isn't separately verified in the fact-check beyond upload. |
| 15 | Footer founder line, "Feito na Covilhã", `[nome do fundador]`, `[Covilhã]` | **Removed.** | Gildo 17 Oct: no founder line, no Covilhã. |
| 16 | `[email de contacto]` | **contacto@invoflow.pt** | Resolved in the brief. |
| 17 | Tokens `[desconto]`, `[trimestre do piloto]`, `[canal de suporte]`, `[formato do feedback]`, `[dias até à resposta]` | **Dropped (moot).** | They only existed for the pilot offer and the reply-time promise. |
| 18 | EN closed state "Sign-ups open soon." | **"Registration opens soon."** | check.mjs:108 requires that exact EN string; v3's EN would have failed the gate. |
| 19 | Hero sub "…organiza um pack para o seu contabilista." | "…organiza um pack **para enviar ao seu contabilista**." | Keeps check.mjs:43 (`'pack para enviar ao seu contabilista'`) green without a QA change. |
| 20 | Nav "Como funciona · Piloto · Perguntas" | "Como funciona · Limites · Perguntas" | No pilot section. |
| 21 | (none) | **New:** interest-list privacy lines (§7b), demo poster line, closed-state hero helper, meta title/description, OG text, error states incl. rate limit. | Brief deliverables; chrome labels moved from CVO to this seat (BOT-PROPOSAL §10 gap 6). |
| 22 | Step 3 "Quem fecha a declaração continua a ser ele." | "Quem fecha a declaração continua a ser o seu contabilista." | Gender-neutral, same meaning. |
| 23 | "Revê…" / review wording | Unchanged from v3 ("As leituras claras ficam logo marcadas como prontas… Pode abrir, rever e corrigir qualquer fatura."). | Already matches the fact-check and CVO's "pode rever e corrigir". |

### v4.1 (CVO's recorded calls, 21:40 Lisbon; Invoflow Operator status)

| # | Change | Why |
|---|---|---|
| 4.1-1 | Hooks 1, 2, 5 marked **APPROVED** for the Meta test; hook 3 reserve; **hook 4 OUT** | CVO: "o original fica guardado" is a retention claim until the privacy fix lands |
| 4.1-2 | Ad-set description fixed: PT "É uma estimativa. Não substitui o contabilista." + EN "It's an estimate. It doesn't replace your accountant." | CVO |
| 4.1-3 | Meta button = **Registar-se** (was "Saiba mais or Registar-se, CVO picks") | CVO: pre-filters for intent; CTR judged with this button |
| 4.1-4 | **Hero caveat micro-line added** under the friction line: "É uma estimativa. Não substitui o contabilista." / "It's an estimate. It doesn't replace your accountant." No "cálculo". Partly reverses changelog row 6 | CVO (for-gildo A4) |
| 4.1-5 | FAQ 7 price-free rewrite marked **DECIDED** | CVO (A7) |
| 4.1-6 | Form dev note: consent timestamp + consent text version stored; no outbound email; thank-you Variant A ships | Invoflow Operator |
| 4.1-8 | **Hero example figures APPROVED and filled in:** − 41,86 / 230,00 / 188,14, rows 23,00 / 4,60 / 11,50 / 2,76 on 100,00 / 20,00 / 50,00 / 12,00, vendors "Exemplo, Lda", "Papelaria Fictícia", "Oficina Exemplo", "Gráfica Modelo", period "T4 · 2026", labelled "Exemplo · dados fictícios" / "Example · fictional data". Replaces the v4 token (changelog row 12) | Gildo approval 2026-10-17 21:41, this case only |
| 4.1-7 | Triage moved to an optional one-click question in the welcome email (COPY-v4-emails.md), never on the form | CVO segment split for the later pilot-plus-price email |

### v4.2 (CVO, 21:44 Lisbon): retention wording dropped

| # | Change | Why |
|---|---|---|
| 4.2-1 | Step 1: "O original fica guardado." → **"O original segue no pack para o contabilista."** / "The original is kept." → **"The original goes in your accountant's pack."** | No retention claim until the privacy fix and Gildo's retention answer; keeps the verified fact that originals go in the ZIP |
| 4.2-2 | Gains 2: "Fotografou, ficou guardado." → **"Fotografou, está no pack."** / "Photographed means kept." → **"Snap it, and it's in the pack."** | Same |
| 4.2-3 | Hook 4: "…O original fica guardado." → **"…O original segue no pack."** (115 chars) / EN "…The original goes in the pack."; status OUT → **reserve, not in the test** | Same |
| 4.2-4 | Emails: welcome item 1 and nurture 1 reworded the same way (PT and EN) | Same |

Retention wording ("fica guardado", "is kept") comes back only after the privacy fix lands **and** Gildo answers the retention question (for-gildo A2).

Note on honest limits: the hero now carries one short caveat and §5 carries the full limits. That's a deliberate CVO call (guard next to the strong H1), not a repeat of v3's four disclaimers.

Pain section (§2), how-it-works steps 1–2 and gains (§4) keep COPY-v3's voice almost word for word: they work.

---

## Section outline (v4)

| # | Section | Job | Main elements |
|---|---------|-----|---------------|
| 0 | Chrome | Find your way, switch language | skip link, wordmark, nav, PT/EN toggle, header CTA |
| 1 | Hero | Name the pain-led promise, one low-commitment CTA | eyebrow, H1, sub, CTA, friction line, caveat micro-line, demo link, example sheet (token figures) |
| 2 | Pain | Reader recognises their own quarter | H2, 4 scenes, closing line |
| 3 | How it works | Exactly what Invoflow does | H2, 3 steps, demo video + caption + poster line |
| 4 | Gains | What changes for them | H2, 4 cards |
| 5 | Limits | Honest limits, said once | H2, intro, 6 lines |
| 6 | FAQ | Remove the remaining objections | 8 accordion items |
| 7 | Interest list | The ask (repeat of the hero CTA) | title, intro, "O que recebe", email + consent, closed/open states, errors, thank-you, privacy lines |
| 8 | Footer | Trust + legal | one line, links, contact, entity token |

---

## 0. Chrome and meta

### PT-PT
- **Meta title:** Invoflow: acabe com as surpresas de IVA no fim do trimestre
- **Meta description:** Fotografe as faturas ao longo do trimestre e veja uma estimativa do IVA. Deixe o email para saber quando a Invoflow abrir.
- **OG title:** Acabe com as surpresas de IVA no fim do trimestre.
- **OG description:** Fotografe as faturas, veja uma estimativa do IVA e envie um pack organizado ao seu contabilista.
- **Skip link:** Saltar para o conteúdo
- **Nav (aria-label "Secções"):** Como funciona · Limites · Perguntas
- **Language group (aria-label):** Idioma / Language · buttons "PT" / "EN"
- **Header CTA (small):** Avisem-me
- **Wordmark link label (sr-only):** Invoflow, início
- **noscript:** Ative o JavaScript para usar o formulário.

### EN
- **Meta title:** Invoflow: stop the VAT surprises at the end of the quarter
- **Meta description:** Photograph your invoices as the quarter goes and see a VAT estimate. Leave your email to hear when Invoflow opens.
- **OG title:** Stop the VAT surprises at the end of the quarter.
- **OG description:** Photograph your invoices, see a VAT estimate and send your accountant an organised pack.
- **Skip link:** Skip to content
- **Nav (aria-label "Sections"):** How it works · Limits · Questions
- **Language group (aria-label):** Idioma / Language · buttons "PT" / "EN"
- **Header CTA (small):** Keep me posted
- **Wordmark link label (sr-only):** Invoflow, home
- **noscript:** Turn on JavaScript to use the form.

> Dev note: v3's noscript "Com o endpoint vazio, nada é guardado" was a developer note (CRITIQUE P0-2); dropped.

---

## 1. Hero

### PT-PT
- **Eyebrow:** Para ENI e microempresas com IVA trimestral
- **H1:** Acabe com as surpresas de IVA no fim do trimestre.
- **Sub:** Fotografe as faturas ao longo do trimestre. A Invoflow lê os dados, mostra uma estimativa do IVA e organiza um pack para enviar ao seu contabilista.
- **CTA (primary, → `#lista`):** Avisem-me
- **Friction line (under the CTA):** Só pedimos o email. Sem compromisso.
- **Caveat micro-line (under the friction line, small):** É uma estimativa. Não substitui o contabilista.
- **Secondary link (quiet, → `#demonstracao`):** Ver a demonstração (18 s)

### EN
- **Eyebrow:** For sole traders and micro-companies in Portugal that file VAT quarterly
- **H1:** Stop the VAT surprises at the end of the quarter.
- **Sub:** Photograph your invoices as the quarter goes. Invoflow reads them, shows a VAT estimate and puts together an organised pack to send to your accountant.
- **CTA (primary, → `#lista`):** Keep me posted
- **Friction line:** Just your email. No commitment.
- **Caveat micro-line (small):** It's an estimate. It doesn't replace your accountant.
- **Secondary link:** Watch the demo (18 s)

### Hero example sheet (DESIGN-SPEC §3 "Ledger sheet")

> **APPROVED by Gildo, 2026-10-17 21:41 Lisbon, this case only:** the fictional set below (figures, vendor names, period), labelled "Exemplo · dados fictícios" / "Example · fictional data". Don't reuse these numbers elsewhere (ads, emails, video) without a new approval. Row dates and net amounts are the ones in UI Lead's mock (`invoflow-landing-design/mock/index.html:71-79`), the same set. Arithmetic: 23,00 + 4,60 + 11,50 + 2,76 = 41,86; 230,00 − 41,86 = 188,14; each row is 23 % of its net amount (100,00 / 20,00 / 50,00 / 12,00). The amounts stay inside the sheet under the "Estimativa de IVA" heading and the "Exemplo" flag; the total row says "Estimativa".

#### PT-PT
- **Sheet eyebrow:** Estimativa de IVA
- **Period:** T4 · 2026
- **Flag chip:** Exemplo · dados fictícios
- **Columns:** Data · Fornecedor · Base (EUR) · IVA (EUR)
- **Rows:**
  | Data | Fornecedor | Base (EUR) | IVA (EUR) |
  |---|---|---|---|
  | 03/10 | Exemplo, Lda | 100,00 | 23,00 |
  | 14/10 | Papelaria Fictícia | 20,00 | 4,60 |
  | 06/11 | Oficina Exemplo | 50,00 | 11,50 |
  | 21/11 | Gráfica Modelo | 12,00 | 2,76 |
- **Footer row 1:** IVA das faturas de despesas · − 41,86
- **Footer row 2:** IVA das vendas (introduzido por si) · 230,00
- **Total row:** Estimativa do IVA a entregar · 188,14 (double rule)
- **Pack chip:** Pack para o contabilista · ZIP · originais · CSV · PDF
- **Caption:** Exemplo ilustrativo com dados fictícios.
- **Table caption (sr-only):** Exemplo de uma estimativa de IVA de um trimestre, com dados fictícios.

#### EN
- **Sheet eyebrow:** VAT estimate
- **Period:** T4 · 2026 (keep the PT quarter label "T4" in both languages, or use "Q4 · 2026" in EN; UI Lead's call, the figures don't change)
- **Flag chip:** Example · fictional data
- **Columns:** Date · Supplier · Net (EUR) · VAT (EUR)
- **Rows:** same four rows as PT (dates, fictional vendor names and amounts unchanged; vendor names aren't translated).
- **Footer row 1:** VAT on your expense invoices · − 41,86
- **Footer row 2:** VAT on sales (entered by you) · 230,00
- **Total row:** Estimated VAT to hand over · 188,14
- **Pack chip:** Pack for your accountant · ZIP · originals · CSV · PDF
- **Caption:** Illustrative example with fictional data.
- **Table caption (sr-only):** Example of one quarter's VAT estimate, with fictional data.

> Currency stays in the column headers only (no `€` beside a digit), as DESIGN-SPEC §3 already does, so check.mjs' euro rule isn't touched by the sheet. Amounts keep comma decimals (PT format) in both languages, as in the mock.

---

## 2. Pain (from v3, unchanged)

### PT-PT
**H2:** Conhece este fim de trimestre?

1. **A caça às faturas.**
   Estão na carteira, no porta-luvas, numa gaveta e perdidas no email. Um domingo à noite vai-se a juntá-las.
2. **O talão que já não se lê.**
   O papel térmico desbotou. A fatura do gasóleo ficou no casaco e foi para a máquina. Aquela despesa fica pelo caminho.
3. **O telefonema do contabilista.**
   "Falta-me a fatura de fevereiro." Volta a procurar, fotografa à pressa, envia por WhatsApp, e depois falta outra.
4. **O número que chega tarde.**
   Só fica a saber quanto IVA vai entregar quando o contabilista lhe diz. Nessa altura, o dinheiro já tinha outro destino.

**Closing line:** O problema não são as contas. São os papéis espalhados e um número que só aparece quando já é tarde para planear.

### EN
**H2:** Sound like your quarter-end?

1. **The invoice hunt.**
   They're in your wallet, the glovebox, a drawer and lost somewhere in your email. A Sunday evening goes on rounding them up.
2. **The receipt you can't read any more.**
   The thermal paper has faded. The fuel receipt stayed in a jacket pocket and went through the wash. That expense quietly disappears.
3. **The call from your accountant.**
   "I'm missing February's invoice." You search again, snap a rushed photo, send it on WhatsApp, and then another one is missing.
4. **The number that arrives too late.**
   You only find out how much VAT you'll hand over when your accountant tells you. By then, that money already had other plans.

**Closing line:** The problem isn't the maths. It's scattered paper, and a number that only shows up when it's too late to plan for it.

---

## 3. How it works

### PT-PT
**H2:** Como a Invoflow ajuda

1. **Fotografe ou carregue a fatura**
   Logo que a recebe: tire uma fotografia com o telemóvel ou carregue o PDF que chegou por email. O original segue no pack para o contabilista.
2. **A Invoflow lê e assinala o que rever**
   A Invoflow extrai o fornecedor, a data, os valores e o IVA. Nas fotografias, lê também o código QR da fatura, se estiver nítido. As leituras claras ficam logo marcadas como prontas. As duvidosas ficam assinaladas: um campo em falta, uma leitura pouco segura ou uma possível fatura duplicada. Pode abrir, rever e corrigir qualquer fatura.
3. **Veja a estimativa e envie o pack**
   Introduza o IVA das suas vendas do trimestre. A Invoflow subtrai-lhe o IVA das suas faturas de despesas e mostra uma estimativa do IVA a entregar, que se atualiza à medida que as faturas entram. No fim, descarrega um pack (ZIP com os originais, um resumo em CSV e outro em PDF) e envia-o ao seu contabilista. Quem fecha a declaração continua a ser o seu contabilista.

**Demo (`#demonstracao`)**
- **Play pill / poster line:** Ver a demonstração (18 s)
- **Poster alt text:** Ecrã da Invoflow a mostrar uma fatura de exemplo pronta a rever.
- **Caption under the frame:** Exemplo ilustrativo com dados fictícios.
- **Frame top bar:** Invoflow · 0:18

### EN
**H2:** How Invoflow helps

1. **Photograph or upload the invoice**
   As soon as you get it, take a photo with your phone or upload the PDF that came by email. The original goes in your accountant's pack.
2. **Invoflow reads it and flags what to check**
   Invoflow pulls out the supplier, date, amounts and VAT. On photos it also reads the invoice's QR code when it's sharp enough. Clear reads are marked ready straight away. Doubtful ones are flagged: a missing field, a low-confidence read or a possible duplicate. You can open, review and correct any invoice.
3. **See the estimate, send the pack**
   Type in the VAT on your sales for the quarter. Invoflow subtracts the VAT on your expense invoices and shows an estimate of the VAT to hand over, updating as invoices come in. At the end you download a pack (a ZIP with the originals plus a CSV and a PDF summary) and send it to your accountant. Your accountant still does the filing.

**Demo**
- **Play pill / poster line:** Watch the demo (18 s)
- **Poster alt text:** Invoflow screen showing an example invoice ready to review.
- **Caption under the frame:** Illustrative example with fictional data.
- **Frame top bar:** Invoflow · 0:18

> Dev note (Invoflow Operator): the current recording and its VTT captions show "Prazo de entrega", written dates and "Atrasado 150 dias" (CRITIQUE P0-1, DESIGN-SPEC §5). They need the re-record before ads run, and the new captions must pass the same bans. The mp4 also needs byte-range (206) support or iPhone/Safari won't play it (GATE-live-93fcead P1-1). If the video can't be fixed before launch, hide the demo block and the hero "Ver a demonstração" link together; no other copy depends on it.

---

## 4. Gains (from v3; Gains 1 wording tuned)

### PT-PT
**H2:** O que muda para si

1. **Um número antes do fim do trimestre**
   Em vez de esperar pelo telefonema, introduz o IVA das vendas e vê uma estimativa do IVA a entregar enquanto o trimestre decorre. Assim consegue planear a tesouraria com tempo.
2. **As faturas num só sítio**
   Fotografou, está no pack. Acabaram as gavetas, os porta-luvas e os talões desbotados.
3. **Menos idas e voltas com o contabilista**
   Entrega tudo de uma vez, organizado e com os originais. Os pedidos de "falta-me esta" devem diminuir.
4. **O fim do trimestre deixa de ser uma caça**
   Passa a ser um envio: descarregar o pack e mandar.

### EN
**H2:** What changes for you

1. **A number before the quarter ends**
   Instead of waiting for the call, you enter your sales VAT and see an estimate of the VAT to hand over while the quarter is still running, so you can plan your cash with time to spare.
2. **Your invoices in one place**
   Snap it, and it's in the pack. No more drawers, gloveboxes or faded receipts.
3. **Less back-and-forth with your accountant**
   You hand everything over in one go, organised, with the originals. The "I'm missing this one" requests should drop.
4. **Quarter-end stops being a hunt**
   It becomes a send: download the pack and pass it on.

---

## 5. Limits (the one deliberate place; replaces v3 §5 Pilot)

### PT-PT
**H2:** Limites, com honestidade
**Intro:** Antes de deixar o email, saiba o que a Invoflow faz e o que não faz.

- **É uma estimativa.** O IVA das vendas é introduzido por si. A Invoflow subtrai-lhe o IVA das suas faturas de despesas e mostra o resultado como estimativa. Não é uma declaração nem um valor oficial.
- **A leitura automática pode errar.** Talões desbotados, escritos à mão ou com um código QR pequeno podem sair mal lidos. As leituras claras ficam logo prontas; as outras ficam assinaladas. Pode rever e corrigir qualquer fatura.
- **Não substitui o contabilista** e não é aconselhamento fiscal.
- **Não envia nada às Finanças** e não está ligada ao e-Fatura.
- **Funciona no navegador**, também no telemóvel, e pode adicioná-la ao ecrã principal. Não há app nas lojas.
- **Pensada para o IVA trimestral.** Se entrega o IVA todos os meses, deixe o email na mesma: a Invoflow também mostra períodos mensais, mas foi pensada para o fim do trimestre.

### EN
**H2:** Honest limits
**Intro:** Before you leave your email, here's what Invoflow does and doesn't do.

- **It's an estimate.** You type in your sales VAT. Invoflow subtracts the VAT on your expense invoices and shows the result as an estimate. It isn't a tax return or an official figure.
- **Automatic reading can get things wrong.** Faded or handwritten receipts, or ones with a small QR code, may be misread. Clear reads are marked ready straight away; the rest are flagged. You can review and correct any invoice.
- **It doesn't replace your accountant** and it isn't tax advice.
- **It sends nothing to the tax authority** and isn't connected to e-Fatura.
- **Runs in your browser**, on your phone too, and you can add it to your home screen. There's no app-store app.
- **Built for quarterly VAT.** If you file VAT every month, leave your email anyway: Invoflow shows monthly periods too, but it was built around quarter-end.

---

## 6. FAQ

> **FAQ 7: DECIDED** (CVO, 21:40 Lisbon): keep the price-free answer below in PT and EN. Annotation only, not visible copy.

### PT-PT
**H2:** Perguntas frequentes

1. **A Invoflow substitui o meu contabilista?**
   Não. A Invoflow organiza as suas faturas e mostra uma estimativa. A declaração e as decisões fiscais continuam com o seu contabilista.
2. **O valor de IVA que aparece é oficial?**
   Não. É uma estimativa. Introduz o IVA das suas vendas e a Invoflow subtrai-lhe o IVA das faturas de despesas que carregou. Enquanto não introduzir o IVA das vendas, vê apenas o IVA das suas compras. O valor final é o que o seu contabilista apurar.
3. **A Invoflow envia alguma coisa às Finanças?**
   Não. Não comunica com a Autoridade Tributária nem com o e-Fatura. O pack fica consigo e é enviado por si ao contabilista.
4. **E se a fotografia sair mal ou o talão estiver desbotado?**
   A Invoflow assinala as leituras pouco seguras e os campos em falta. Pode corrigir à mão, e o original vai no pack.
5. **Também funciona com as faturas que recebo em PDF por email?**
   Sim. Pode carregar o PDF tal como chegou, ou uma fotografia.
6. **O que recebe o meu contabilista?**
   Um ficheiro ZIP com os originais das faturas, um resumo em CSV (para abrir numa folha de cálculo) e um resumo em PDF. As faturas que ainda não reviu vão marcadas como tal. O seu contabilista não precisa de conta nem de instalar nada, e não tem acesso à Invoflow: recebe apenas o ficheiro que lhe enviar.
7. **Quanto vai custar?**
   Ainda não há preço público. Quando houver, quem está na lista sabe por email. Deixar o email não o compromete a nada, e esta página não cobra nada.
8. **Onde ficam os meus dados?**
   [alojamento e retenção: local de alojamento, tempo de conservação, quem tem acesso — aguarda decisão do Gildo]. O email que deixar aqui serve apenas para lhe escrevermos sobre a Invoflow, e pode sair da lista a qualquer momento. Mais detalhes na «política de privacidade» → /privacy/.

### EN
**H2:** Frequently asked questions

1. **Does Invoflow replace my accountant?**
   No. Invoflow organises your invoices and shows an estimate. The filing and the tax decisions stay with your accountant.
2. **Is the VAT figure official?**
   No. It's an estimate. You enter the VAT on your sales, and Invoflow subtracts the VAT on the expense invoices you've uploaded. Until you enter your sales VAT, you only see the VAT on your purchases. The final figure is whatever your accountant works out.
3. **Does Invoflow send anything to the tax authority?**
   No. It doesn't talk to the tax authority or to e-Fatura. The pack stays with you, and you send it to your accountant.
4. **What if the photo is bad or the receipt has faded?**
   Invoflow flags low-confidence reads and missing fields. You can correct them by hand, and the original goes in the pack.
5. **Does it work with invoices I get as PDFs by email?**
   Yes. You can upload the PDF as it arrived, or a photo.
6. **What does my accountant receive?**
   A ZIP with the original invoices, a CSV summary (for any spreadsheet) and a PDF summary. Invoices you haven't reviewed yet are marked as such. Your accountant doesn't need an account or any software and has no access to Invoflow: they only get the file you send them.
7. **How much will it cost?**
   There's no public price yet. When there is, people on the list hear about it by email. Leaving your email doesn't commit you to anything, and this page doesn't charge anything.
8. **Where is my data kept?**
   [hosting and retention: location, retention period, who has access — awaiting Gildo's decision]. The email you leave here is used only to write to you about Invoflow, and you can leave the list at any time. More in the «privacy policy» → /privacy/.

---

## 7. Interest list (`#lista`; the repeat of the hero CTA)

> **DEV NOTE**
> - **Two states.** **CLOSED** ships until signups pass QA (GATE-93fcead P1-1 and P1-2 fixed and re-gated) **and** Gildo approves going public. In CLOSED, the email field, consent and button sit in a disabled fieldset and **no POST** is possible. **OPEN** is the same block with the fieldset enabled.
> - **Fields:** `email` (required) + `consent` (required checkbox, **unticked** by default). Nothing else. Keep the hidden honeypot unchanged. UTMs and page language may still be captured silently (they're in the privacy lines below).
> - **Backend:** `qualify.js` `parseAnswers()` currently returns `null` (→ 400) when name, regime, volume or accountant is missing (`qualify.js:27-29`), so an email-only form fails today. Invoflow Operator's change. `isQualified()` has nothing to work on.
> - **Duplicate email, honeypot hit and new signup must show the identical success state** (same heading, body, element and focus), and the API must return the identical body (GATE-93fcead P1-2 fix).
> - **Consent record (Invoflow Operator, v4.1):** the page stores the consent timestamp and the consent text version with each signup. **No outbound email** until Gildo picks an email tool; so Variant A of the thank-you ships, and double opt-in and unsubscribe come with the tool.
> - Rate-limited (429) and network errors show the send error; they never reveal whether the email exists.

### PT-PT
- **Section kicker (aria-hidden):** 07
- **Title (H2):** Quer saber quando a Invoflow abrir?
- **Intro:** Deixe o seu email. Escrevemos-lhe quando houver novidades e quando a Invoflow abrir.
- **List title:** O que recebe
  - Alguns emails curtos sobre como a Invoflow funciona.
  - O aviso quando a Invoflow abrir.
  - Uma forma simples de sair da lista, em qualquer email.
- **Email:** label "Email" · placeholder "nome@exemplo.pt" · helper "Só pedimos o email."
- **Consent (checkbox, required, unticked):** "Aceito receber emails da Invoflow sobre o produto e o seu lançamento. Posso sair da lista a qualquer momento. Li a «política de privacidade» → /privacy/."
- **Submit:** Avisem-me
- **Under the button:** Sem spam. Não partilhamos o seu email.

**CLOSED state (ships now)**
- **Status (bold):** Inscrições abrem em breve.
- **Status (body):** Estamos a terminar os últimos testes ao formulário.
- **Optional extra line (Gildo/Invoflow Operator decide):** Entretanto, pode escrever-nos para contacto@invoflow.pt.

**OPEN state: errors** (announced on submit, linked by `aria-describedby`)
- **Email empty:** Indique o seu email.
- **Email invalid:** Este email não parece completo. Verifique-o, por favor.
- **Consent not ticked:** Para entrar na lista, marque a caixa de consentimento.
- **Send error (network, 5xx, 429):** Não foi possível enviar. Tente outra vez daqui a pouco.
- **Submitting (sr-only, `aria-busy`):** A enviar…

**OPEN state: success = duplicate = honeypot (identical)**
- *Variant A, no double opt-in (until Invoflow Operator builds it):*
  - **Heading:** Obrigado. Está na lista.
  - **Body:** Quando houver novidades sobre a Invoflow, escrevemos-lhe para este email. Pode sair da lista a qualquer momento.
- *Variant B, with double opt-in (recommended):*
  - **Heading:** Obrigado. Falta só um passo.
  - **Body:** Se for a primeira vez que se inscreve, vai receber um email de confirmação. Abra-o e carregue em «Confirmar». Se não o encontrar, veja a pasta de spam ou de promoções.

### EN
- **Title (H2):** Want to know when Invoflow opens?
- **Intro:** Leave your email. We'll write when there's news and when Invoflow opens.
- **List title:** What you get
  - A few short emails about how Invoflow works.
  - A heads-up when Invoflow opens.
  - An easy way to leave the list, in every email.
- **Email:** label "Email" · placeholder "name@example.com" · helper "Just your email."
- **Consent (checkbox, required, unticked):** "I agree to receive emails from Invoflow about the product and its launch. I can leave the list at any time. I've read the «privacy policy» → /privacy/."
- **Submit:** Keep me posted
- **Under the button:** No spam. We don't share your email.

**CLOSED state**
- **Status (bold):** Registration opens soon.
- **Status (body):** We're finishing the last tests on the form.
- **Optional extra line:** In the meantime, you can write to contacto@invoflow.pt.

**OPEN state: errors**
- **Email empty:** Enter your email.
- **Email invalid:** That email doesn't look complete. Please check it.
- **Consent not ticked:** To join the list, tick the consent box.
- **Send error:** We couldn't send that. Please try again in a moment.
- **Submitting (sr-only):** Sending…

**OPEN state: success = duplicate = honeypot (identical)**
- *Variant A, no double opt-in:*
  - **Heading:** Thanks. You're on the list.
  - **Body:** When there's news about Invoflow, we'll write to this email. You can leave the list at any time.
- *Variant B, with double opt-in:*
  - **Heading:** Thanks. One more step.
  - **Body:** If this is your first time signing up, you'll get an email to confirm your address. Open it and click "Confirm". If you can't find it, check your spam or promotions folder.

> Why Variant B's body is conditional: an already-listed address must see the same words as a new one (P1-2), and "we've sent you an email" would be false for it unless the backend sends something on duplicates too. Invoflow Operator chooses the backend behaviour; the words stay true either way.

### 7b. Interest-list privacy lines (for `/privacy/`; Invoflow Operator ships, Gildo approves)

#### PT-PT
- **Título:** Lista de interesse
- **O que guardamos:** o email que indicar, a data e a confirmação do seu consentimento, a língua da página e, se existir, a campanha de onde veio (parâmetros utm).
- **Para quê:** só para lhe escrevermos sobre a Invoflow e o seu lançamento. Não vendemos nem partilhamos o seu email para publicidade de terceiros.
- **Base legal:** o seu consentimento, que pode retirar a qualquer momento.
- **Como sair:** com o link no fundo de cada email, ou escrevendo para contacto@invoflow.pt. Depois disso, deixamos de lhe escrever.
- **Onde e durante quanto tempo:** [alojamento e retenção da lista: onde fica guardada, durante quanto tempo, o que acontece quando sai — aguarda decisão do Gildo].
- **Proteção contra abusos:** [texto sobre o endereço IP — aguarda correção técnica: hoje é guardado um resumo SHA-256 sem sal, que é reversível (GATE-93fcead P2-2), e no D1 não expira (P2-3)].
- **Responsável pelo tratamento:** Hermenegildo Santos · NIF 296556513 · contacto@invoflow.pt

#### EN
- **Title:** Interest list
- **What we keep:** the email you enter, the date and record of your consent, the page language and, if present, the campaign you came from (utm parameters).
- **What for:** only to write to you about Invoflow and its launch. We don't sell or share your email for third-party advertising.
- **Legal basis:** your consent, which you can withdraw at any time.
- **How to leave:** use the link at the bottom of any email, or write to contacto@invoflow.pt. After that, we stop writing to you.
- **Where and for how long:** [interest-list hosting and retention: where it's stored, for how long, what happens when you leave — awaiting Gildo's decision].
- **Abuse protection:** [IP address wording — awaiting a technical fix: today an unsalted SHA-256 summary is stored, which is reversible (GATE-93fcead P2-2), and in D1 it never expires (P2-3)].
- **Data controller:** Hermenegildo Santos · NIF 296556513 · contacto@invoflow.pt

---

## 8. Footer

### PT-PT
- Invoflow: estimativa de IVA e pack de faturas para o seu contabilista. Não é aconselhamento fiscal.
- Privacidade · Contacto: contacto@invoflow.pt
- Hermenegildo Santos · NIF 296556513

### EN
- Invoflow: a VAT estimate and an invoice pack for your accountant. Not tax advice.
- Privacy · Contact: contacto@invoflow.pt
- Hermenegildo Santos · NIF 296556513

---

## Ad hooks (PT-PT for running; EN for reference only, not to be run as-is), ≤125 characters, no price

**Status (CVO, 21:40 Lisbon):** hooks **1, 2 and 5 APPROVED** for the Meta demand test (€120, 14 days, metric visit → signup). Hook 3 is a reserve. Hook 4 was OUT at 21:40 (retention claim); **rewritten at 21:44 without retention wording and now a reserve, not in the test.** What each one tests is in `COPY-v4-hierarchy.md`.

| # | PT-PT (to run) | Angle | EN (reference) |
|---|---|---|---|
| 1 ✅ APPROVED | Faturas no porta-luvas e o IVA só aparece no fim do trimestre? Fotografe-as já e veja uma estimativa ao longo do trimestre. | Paper chaos | Invoices in the glovebox and the VAT only shows up at quarter-end? Snap them now and see an estimate as the quarter goes. |
| 2 ✅ APPROVED | O seu contabilista volta a pedir «a fatura de fevereiro»? Fotografe as faturas e entregue-lhe um pack organizado. | Accountant chase | Your accountant asking for "February's invoice" again? Photograph your invoices and hand over an organised pack. |
| 3 (reserve) | Saiba uma estimativa do seu IVA antes do fim do trimestre. Para ENI e microempresas. Deixe o email e avisamos. | Early number + ICP callout | Get an estimate of your VAT before the quarter ends. For sole traders and micro-companies. Leave your email and we'll tell you. |
| 4 (reserve, not in the test) | O talão desbotou e aquela despesa ficou pelo caminho? Fotografe a fatura quando a recebe. O original segue no pack. | Lost expense | The receipt faded and that expense slipped away? Photograph the invoice when you get it. The original goes in the pack. |
| 5 ✅ APPROVED | Acabe com as surpresas de IVA no fim do trimestre. Veja uma estimativa enquanto o trimestre decorre. Só pedimos o email. | Promise (matches H1) | Stop the VAT surprises at quarter-end. See an estimate while the quarter is running. All we ask is your email. |

- **Description on every ad set (CVO, decided):** PT "É uma estimativa. Não substitui o contabilista." · EN reference "It's an estimate. It doesn't replace your accountant."
- **Meta button (CVO, decided):** **Registar-se** (EN reference: "Sign up"). CVO's call: it pre-filters for intent. CTR benchmarks are judged with this button. The landing page's own CTA stays "Avisem-me".
- **Landing URL for ads:** `https://invoflow.pt/?utm_source=meta&utm_medium=paid&utm_campaign=[nome da campanha]&utm_content=hook1…hook5` so signups can be attributed per hook (Invoflow Operator confirms the UTM fields stored).

---

## Verification log (script-run on this file; see the command in `COPY-v4-claims.md`)
- Banned on the visible page (check.mjs list): none in the PT/EN copy sections. "Prazo" and dated strings appear only in dev notes quoting the current video (not visible copy).
- Substring trap: check.mjs bans "a confirmar" case-insensitively, so "para confirmar" fails. v4 uses "um email de confirmação" instead. Anyone editing the copy must keep that in mind.
- "calcula": none. "cálculo" appears only in "folha de cálculo" (spreadsheet), FAQ 6.
- "IVA dedutível": none in visible copy (only in this changelog and dev notes).
- `€` next to a digit: none in visible copy.
- Every sentence about the IVA figure says estimativa / estimate.
- No testimonials, logos, user counts, savings, percentages, time-saved figures or written dates. The only numbers are "18 s" / "0:18" (demo length), section ordinals, and the hero sheet's fictional example set (Gildo-approved 21:41, labelled "Exemplo · dados fictícios"; row dates in dd/mm form, which the check.mjs date ban doesn't match).
- PT-PT: fatura, contabilista, telemóvel, ecrã, descarregar, ficheiro; no "você"; no PT-BR forms. EN is British (organised, organise).
- Ad hooks ≤125 characters (counts in `COPY-v4-hierarchy.md`).

### v4.1 re-scan (2026-10-17 ~21:45 Lisbon)
- check.mjs bans (check.mjs:17-27) over the visible PT/EN copy (§0 to §8 + ad hooks, `>` notes excluded) and over the email drafts: **0 hits**.
- Extra scans: "calcula" 0; "IVA dedutível" 0; "você" 0. "cálculo" only in "folha de cálculo" (spreadsheet; FAQ 6 and nurture 3), not the CVO-banned verb. `€`+digit only in the internal note "€120" about CVO's ad budget (not page copy).
- New hero micro-line "É uma estimativa. Não substitui o contabilista." / "It's an estimate. It doesn't replace your accountant.": no banned terms, no "cálculo".
- Hero sheet: amounts in comma format with no `€`; row dates "03/10", "14/10", "06/11", "21/11" don't match the written-date ban; the total says "Estimativa".
- Visible tokens left: hosting/retention (FAQ 8, privacy ×2 each language), entity/NIF, IP-address wording, and `[nome da campanha]` (ad UTM, not on the page).
- Hooks 1/2/3/4/5: 123/113/110/115/120 characters (hook 4 OUT).

### v4.2 re-scan (~21:46 Lisbon)
- check.mjs bans + "calcula" over visible page copy and email drafts: 0 hits.
- "guardad": 0 in product copy; only inside the two open privacy tokens (hosting/retention and IP wording), which describe the pending question and never ship.
- Hook 4: 115 characters (reserve, not in the test).

### Controller identity (2026-10-20)
- Gildo trades as a sole trader (ENI) under Hermenegildo Santos, NIF 296556513. §7b and the footer use that line. Hosting/retention and the IP wording stay open.
