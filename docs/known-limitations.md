# Known limitations

Suggestions on a receipt are inert text. They never set the document type or the number, and nothing on the review screen applies them in one tap.

## Series token

After a leading `FT`, `FS`, `FR`, `NC` or `ND`, every run of characters that are not letters or digits is a separator, and so are `º` and `°`. `NC. 2026/5`, `NC..2026/5`, `NC;2026/5`, `NC'2026/5`, `NC*2026/5`, `NC+2026/5`, `NC(2026)5`, `NC[1]`, `NCº1` and `NC°1` are all the NC series. `º` is read before NFKC, because NFKC turns it into the letter `o`.

There is one exception. When the code is in title case or lowercase, a run that holds a dot and is not followed by a letter is an abbreviation, not a series: `Fr.12`, `Fr. 12`, `Fs.12`, `Nc.12`, `nd.2026`. In uppercase it is a series: `NC.2026/5`, `NC.1`, `ND.5/1`, `FT.12`, `FT.2026/12`. A dot then a letter is a series in any case (`fr.a`). That case split is what keeps those abbreviations from being treated as a credit note or an invoice series. `frete 12` is a word: letters continue after `fr`, so it is not a series.

The e-Fatura identity is built from the same parse as the series check. It splits a number into code, series and sequence. `FTA/5` and `FT A/5` are both FT, series A, sequence 5, so they are one invoice. `NCB/12` is NC, series B, and matches `NC B/12`. `NC; 2026/005` and `NC 2026/5` are one invoice. A code glued to digits or letters is always split off for the identity. `FT2026/12` matches `FT 2026/12`, and `FTFT/1` matches `FT FT/1`, but the series check still reads them as vendor numbering. `FTA 2026/5` matches `FT A 2026/5` the same way, as on main, though the series check reads `FTA 2026/5` as vendor numbering. Leading zeros still come off only the sequence after the last `/`, and inner spaces stay.

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
