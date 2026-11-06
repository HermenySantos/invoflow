# Known limitations

Suggestions on a receipt are inert text. They never set the document type or the number, and nothing on the review screen applies them in one tap.

## Series token

After a leading `FT`, `FS`, `FR`, `NC` or `ND`, every run of characters that are not letters or digits is a separator, and so are `º` and `°`. `NC. 2026/5`, `NC..2026/5`, `NC;2026/5`, `NC'2026/5`, `NC*2026/5`, `NC+2026/5`, `NC(2026)5`, `NC[1]`, `NCº1` and `NC°1` are all the NC series. `º` is read before NFKC, because NFKC turns it into the letter `o`.

There is one exception. When the code is in title case or lowercase, a run that holds a dot and is not followed by a letter is an abbreviation, not a series: `Fr.12`, `Fr. 12`, `Fs.12`, `Nc.12`, `nd.2026`. In uppercase it is a series: `NC.2026/5`, `NC.1`, `ND.5/1`, `FT.12`, `FT.2026/12`. A dot then a letter is a series in any case (`fr.a`). That case split is what keeps those abbreviations from being treated as a credit note or an invoice series. `frete 12` is a word: letters continue after `fr`, so it is not a series.

The e-Fatura identity is built from the same parse as the series check. It splits a number into code, series and sequence. `FTA/5` and `FT A/5` are both FT, series A, sequence 5, so they are one invoice. `NCB/12` is NC, series B, and matches `NC B/12`. `NC; 2026/005` and `NC 2026/5` are one invoice. A code glued to digits or letters is always split off for the identity. `FT2026/12` matches `FT 2026/12`, and `FTFT/1` matches `FT FT/1`, but the series check still reads them as vendor numbering. `FTA 2026/5` matches `FT A 2026/5` the same way, as on main, though the series check reads `FTA 2026/5` as vendor numbering. Leading zeros still come off only the sequence after the last `/`, and inner spaces stay.

The type code ignores letter case and the series does not. `ft A/5` is `FT A/5`, but `FT a/5` is a different invoice, because AT allows both upper and lower case series. A mark that follows the space after the code starts the series: `FT -A/5` is not `FT A/5`, while `FT-A/5` and `FT - A/5` still are.

## Linking a scan to an e-Fatura invoice

A scan links when its number has the same identity as the AT invoice. When none matches exactly, a scan may link on a looser key that ignores case and a leading mark in the series (`ft a/5` or `FT -A/5` to `FT A/5`), but only when no other AT invoice from the same supplier shares that key.

A code glued to two or more characters can be read two ways. `FRA2026/12` is FR series `A2026` or the vendor code FRA with series `2026`. Such a scan is not linked when another known AT invoice from the same supplier reads the same with its spaces and case dropped. Known invoices are the ones in this pull, the stored AT rows and earlier link payloads. A scan with one glued letter (`FTA/5`) has only one reading and links as before. A scan already linked to one AT invoice is not linked to a second one.

A scan number that does not show its series' case (`ft a/5`, as OCR often reads it) links only on the looser key. The case shows when the series has an upper case letter (`ft A/5`) or the type code is written in capitals (`FT a/5`). A capital only in the type code (`Ft a/5`) does not count, because the type code ignores case. When both `FT A/5` and `FT a/5` are known, neither is linked to such a scan and both are held for review.

When a link is refused, the AT invoice is stored as its own row in review, and the import warns with the receipt id. When an invoice arrives after its scan was linked to the supplier's other reading, the new row gets the same warning. The earlier link is not undone.

There is one exception. When the arriving invoice has exactly the scan's number (`FT A/5` on a scan of `FT A/5`), an invoice linked earlier only on the looser key (`FT a/5`) moves off the scan to its own AT row in review, with a warning naming the scan. Without the move, one of the two would be lost or counted twice. A glued scan linked to one reading keeps that link, because both readings match it exactly. When the user has a live scan of the moved invoice's own number (`FT a/5`) that could link to it, the invoice moves to that scan instead, and no AT row is created. A link stays on the scan, and the arriving invoice is held instead, when a user edited the scan's amounts after the link was made and the scan's VAT is not the arriving invoice's: the edited amounts may be the linked invoice's.

## AT rows a user renumbered

An AT row's figures are AT's figures for the invoice it was created from. A user may edit its number, NIF or type, but that does not make it another invoice. The importer matches an AT row on the values AT gave it, read from the first user edit in the audit log, never on the edited ones. When AT later sends the invoice whose number the user typed (`FT a/5` edited to `FT A/5`, then the real `FT A/5` arrives), that invoice is stored on its own row in review. Its warning names the edited row, so the list shows "Em revisão". The edited row keeps the user's number and amounts.

PATCH stores the identity of the edited number, so an edit cannot reuse a number another live row has (409). Each pull, and each delete of a scan, first points every edited AT row's identity back at the invoice it holds. A row whose numbers were swapped with another's is written through an empty identity, so the unique index never sees two live rows with one identity. When another live row already holds that invoice, the edited row is left as it is and the pull logs it. The invoice whose number the user typed is then not stored. The import skips it as `ambiguous_duplicate` with a warning naming the edited row, so it is not dropped silently. After the held row exists, editing the edited row's number onto the held row's number again is a 409, so the user resolves the pair by deleting one.

A pull reads the account's edits once, at its start. So a PATCH of a field the pull matches on (NIF, type, number, date or amounts) takes the account's row lock first, as the pull does, and waits for a running pull to commit. The wait is bounded, and all waiters for one hold share the budget, in every worker: a PATCH gets 10 s and a pull 30 s, counted from the earliest of the current holder's start and the oldest waiter's start, then a 503 with PT-PT copy and `Retry-After: 10`, and nothing is saved. So a save retried after its 503, or a third pull behind a second, is refused at once instead of waiting its own 10 s or 30 s again; it does not jump the queue either. At most 3 requests per account wait at a time; the rest try the lock once and get the 503 at once, so a retry storm on one account cannot use up the threadpool or the connection pool that other accounts need. The lock is `FOR NO KEY UPDATE`, so a receipt upload, a new VAT-on-sales entry or a delete that stores an AT row again never waits for a pull; before, the foreign-key check made each one wait out the whole pull, and a delete waiting like that while holding a receipt the pull needed was a deadlock. Any other row-lock wait ends after 30 s. A deadlock or lock timeout that still happens is a 503 with "Outra operação nesta conta estava a decorrer ao mesmo tempo… tente novamente", never a generic 500. Once a transaction holds the lock, Postgres ends it if it sits idle for 30 s or runs one statement for 60 s, so a stuck or stopped worker frees the lock; that pull is rolled back and answers the PT-PT "demorou demasiado" 503 (psycopg2 reports the ended session only as a closed connection, which counts). Every other session ends after 5 min idle inside a transaction. A pull's own run time is not capped: a first pull of 300 invoices takes about 3 s and one of 1000 about 21 s, so a matched edit from the same account during a long first pull gets the 503 and saves on retry. Because the budget counts from the holder's start, an edit made more than 10 s into a long pull is refused at once rather than waiting for the pull's end. Other accounts are not slowed. The handlers run in FastAPI's threadpool, so a lock wait or a long pull never blocks the event loop. With 1000 invoices, another account's `/health` stayed under 0.05 s, against 19.8 s before. Before this, a rename that landed mid-pull linked the arriving invoice to the edited row and doubled the other invoice's VAT. A rename to a number that only an edited row's identity holds, after a pull pointed that row back at its own invoice, is not a 409: no row shows that number, so a swap through a temporary number works with a pull in between. The renamed row keeps its identity until the next pull.

## Clashes the user must resolve

Two states are shown on the rows involved, with a PT-PT warning and an "e-Fatura por resolver" badge in the list, plus one line in the period summary. Neither changes what a row counts towards the totals.

- An invoice skipped as `ambiguous_duplicate`: either several receipts match it, or an edited row has its number while another row holds the invoice that row came from. Every pull examines the skipped invoice again. When the clash is gone (one of the receipts deleted, a number corrected), the next pull stores or links it, and the warning goes.
- An AT row a user renumbered whose original invoice another live row also holds. Both rows may count the same invoice and the invoice the user typed may be missing. Main's old relink wrote this state (the QA's G-1: 9.20 instead of 6.90; G-2: 4.60 instead of 6.90), and so did the mid-pull rename above. Nothing is repaired automatically. The warning on each row names the row to delete: the one that still shows the original AT number, never the edited row. When the user deletes that row, the next pull gives the edited row its identity back and stores the missing invoice on its own row in review. A link that a pull matched on the edited number, not the row's AT number, moves off the row too, also when its key is an ATCUD.
  Deleting the edited row instead does not repair it. The link of the invoice that row stood for still points at it, so a pull treats the invoice as one the user deleted on purpose and reports it unchanged, and with the pair gone both warnings go too (the QA's G-1 then shows 4.60). There is no undelete in the app yet.
- When the only row an `ambiguous_duplicate` warning names is deleted, the warning has no row left to show on, and the summary line goes with it. The invoice is still not stored until the next pull, which stores it (6.90 in the QA's case).

This also repairs an AT row that main merged and a user then edited (`FT A/5` merged with `FT a/5` and edited to `FT a/5`). Migration 014 skipped it, so its link still carried `FT a/5` while its figures were `FT A/5`'s. The next pull splits `FT a/5` off to its own row in review, naming the edited row. An identity is no longer always the shown number's, so a migration that recomputes identities must read the first values from the audit log, as the importer does. Migration 014 does: an edited AT row gets the identity of the invoice AT sent it unless another live row holds it, so re-running 014 after the app realigned rows writes nothing. State that the old relink already wrote is flagged for review, as above, not repaired.

## Rows held for review

On the receipts list, an e-Fatura row held for review shows an "Em revisão" badge, its own number ("e-Fatura FT A/5") and the receipt it may duplicate: "Pode corresponder ao recibo FT A/5 (Loja). Reveja os dois." The badge goes away when the row is confirmed or the receipt is deleted. There is no e-Fatura screen and no action to link the two by hand yet.

How a held row counts today: it is in `total_vat`, next to the receipt it may duplicate, until the user resolves it. The deductible estimate counts only confirmed receipts, so a held row is in the pending figure, with its warning. Whether held rows should count is a product decision that is still open.

## Migration 014

Migration 014 recomputes the e-Fatura identity on every AT row with the series' case kept. A row that 012 or 013 soft-deleted as a duplicate is restored when its new identity differs from the kept row and no live row has it. A document whose links carry more than one invoice under the new identity keeps the matching invoice; each other invoice moves to its AT row (a row the user deleted stays deleted), or to a new AT row in review. A document with links for a single invoice is never changed, even when the scan's number differs only in case. Each restored or new row gets an `efatura_split` entry, and each moved link a warning naming the document it left.

On main, `FT A/5` and `FT a/5` without an ATCUD shared one link key, so the later pull overwrote the link's invoice. On an AT row 014 can see this: the row is `FT A/5` and its link now says `FT a/5`. 014 keeps `FT A/5` on that row and splits `FT a/5` off to a new row in review. A row whose number a user edited is left alone, because a case-only edit looks the same. On a scan it cannot: a scan of `FT A/5` linked to `FT a/5` is also what main did, correctly, when `FT a/5` was the only invoice. 014 leaves such a scan alone. The next pull that brings `FT A/5` moves `FT a/5` to its own row (see the exception above). Until then, `FT a/5` has no row of its own and its VAT is missing. If that period is never pulled again, it stays missing. A second run changes nothing, and downgrading 014 leaves everything as it is.

`NC` or `ND` glued to digits is a series when `/`, `.` or `-` follows (`NC2026/5`, `NC1/5`), when there are two or more digits (`NC2026`, `NC001`, `ND2026`), or when one digit is followed by a space (`NC1 2026`). A bare `NC1` is not a series. `FT` and `FS` glued to digits (`FT2026/1`, `FS2026/12`) stay vendor numbering.

## Retypes on linked rows

A scan that an e-Fatura import linked to an AT invoice has an AT pair. The review screen shows the AT type, and the receipts list shows the AT number.

Retypes are locked on linked rows. Any change to the document type (FT, FS, FR, NC or ND) is refused, whatever number the same edit sends. For example, a row linked to `FT 2026/12` cannot be saved as FS with `FT 2026/12`, `FS 2026/12` or `2026/12`. The API returns 422 with `O n.º do documento não corresponde ao tipo indicado.`, and the review screen shows the same message. The printed-pair confirmation is not offered on a linked row.

An edit that keeps the type, such as a number change, saves as before. A linked row that is still unclassified can take only the AT type, so it can still be confirmed. When the link no longer points at the row, the row can be retyped.

Clearing an accepted printed pair writes a `series_mismatch_cleared` audit entry. Its source is `user` for an edit, `qr` for a QR read, and `efatura` for an e-Fatura link. The `series_mismatch_accepted` entry stays.

## Migration 013

Migration 013 recomputes the e-Fatura identity on every AT row with the current normaliser. It then soft-deletes live duplicates with the same ranking as 012, moves their links, and writes an `efatura_dedupe` entry for each removed row. A second run changes nothing. Downgrading 013 leaves the identities and the removed rows as they are.

## Migration 010

Downgrading migration 010 drops `series_mismatch_accepted`. Rows that had been accepted come back as false and leave the accepted-mismatch list in the summary, the projection, `summary.pdf` and `pares_aceites.csv`. The `series_mismatch_accepted` audit entries are not stored in that column, so they remain.

## Credit and debit suggestions

The credit veto is a keyword list. These wordings still suggest Fatura and `FT A/12` on a page that also has an invoice title:

- `N.C. n.º 7`, `N.C.`, `N. C.`, `N C`, `N|C`, `N\C`
- `N/Crédito`, `N/Créd.`
- `Nota Créd.`, `Nota de Cred.`, `Nota-crédito`
- `Doc. de crédito`, `Documento crédito`
- `Crédito a seu favor`, `Crédito a v/ favor`, `Crédito a seu/v/ favor`
- `Crédito ao cliente`, `Crédito n.º 7`
- `Regularização a favor do cliente`

The same list over-vetoes a plain invoice: `IVA N/C` drops the FT suggestion.

## Series fold

The fold is an enumeration. It covers NFKC, format characters (zero-width space, BOM, soft hyphen, word joiner), the Greek, Cyrillic, small-cap and Lisu letters listed in the series code, combining marks, and the hyphens and slashes U+2010–U+2015, U+2212, U+FE58, U+FE63, U+FF0D, U+2044, U+2215, U+29F8 and U+FF0F.

These are not folded:

- Coptic `ⲚⲤ`, Cherokee `Ꮯ`, `Ƈ`, `Ɲ`
- middle dot `N·C` and `N⸱C`
- backslash `N\C`, box slash `N╱C`
- `NCーA/5`: the long vowel mark is a letter, so it is not a separator
- Hangul filler and braille blank
- a leading `Nº`, `N.º` or `Doc` before `NC A/5`
