# Known limitations

Suggestions on a receipt are inert text. They never set the document type or the number, and nothing on the review screen applies them in one tap.

## Series token

A code followed by `.` and then a digit is a series only when both letters of the code are uppercase: `NC.2026/5`, `NC.1`, `ND.5/1`, `FT.12`, `FT.2026/12`. Title case and lowercase are abbreviations, not a series: `Fr.12`, `Fs.12`, `Nc.12`, `nd.2026`. That case split is what keeps those abbreviations from being treated as a credit note or an invoice series. `frete 12` is a word: letters continue after `fr`, so it is not a series.

`NC` or `ND` glued to digits is a series when `/`, `.` or `-` follows (`NC2026/5`, `NC1/5`), when there are two or more digits (`NC2026`, `NC001`, `ND2026`), or when one digit is followed by a space (`NC1 2026`). A bare `NC1` is not a series. `FT` and `FS` glued to digits (`FT2026/1`, `FS2026/12`) stay vendor numbering.

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
- backslash `N\C` and `NC\A/5`, box slash `N╱C`
- `NC⁃A/5`, `NC⸺A/5`, `NCーA/5`
- Hangul filler and braille blank
- `NC_A/5`, `NC:5`, `NC#5`, `NC,5`, `NC|A/5`, `NC~A/5`
- a leading `Nº`, `N.º` or `Doc` before `NC A/5`
