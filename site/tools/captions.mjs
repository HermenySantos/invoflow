export const q1Deadline = 'Prazo de entrega: 20 de Maio de 2026';
export const q4Deadline = 'Prazo de entrega: 22 de Fevereiro de 2027';

function stamp(ms) {
  const total = Math.max(0, Math.round(ms));
  const pad = (value, width = 2) => String(value).padStart(width, '0');
  const hours = Math.floor(total / 3600000);
  const minutes = Math.floor(total / 60000) % 60;
  const seconds = Math.floor(total / 1000) % 60;
  const millis = total % 1000;
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}.${pad(millis, 3)}`;
}

function render(cues) {
  const lines = ['WEBVTT', ''];
  for (const [start, end, text] of cues) {
    lines.push(`${stamp(start)} --> ${stamp(end)}`, text, '');
  }
  return `${lines.join('\n')}\n`;
}

export function videoTimeline(scenes) {
  let at = 0;
  return scenes.map((scene) => {
    const duration = Math.max(0, scene.end - scene.start);
    const span = { name: scene.name, start: at, end: at + duration };
    at += duration;
    return span;
  });
}

function span(timeline, name) {
  const found = timeline.find((item) => item.name === name);
  if (!found) throw new Error(`missing scene ${name}`);
  return found;
}

export function captionFiles(timeline) {
  const upload = span(timeline, 'upload');
  const preview = span(timeline, 'preview');
  const uploaded = span(timeline, 'uploaded');
  const review = span(timeline, 'review');
  const q4 = span(timeline, 'deadline-q4');
  const q1 = span(timeline, 'estimate-q1');
  const pack = span(timeline, 'pack');
  const pt = render([
    [upload.start, upload.end, 'Carregar uma fatura.'],
    [preview.start, uploaded.end, 'Exemplo ilustrativo. Exemplo, Lda. IVA estimativa 23,00 €. Total 123,00 €.'],
    [review.start, review.end, 'Rever. Exemplo ilustrativo. Exemplo, Lda. NIF 999 999 990. IVA estimativa 23,00 €. Total 123,00 €.'],
    [q4.start, q4.end, `${q4Deadline}. Estimativa. Este valor ignora o IVA das vendas.`],
    [q1.start, q1.end, `${q1Deadline}. Estimativa. IVA dedutível 23,00 €.`],
    [pack.start, pack.end, 'Enviar ao contabilista.'],
  ]);
  const en = render([
    [upload.start, upload.end, 'Upload an invoice.'],
    [preview.start, uploaded.end, 'Illustrative example. Exemplo, Lda. VAT estimate €23.00. Total €123.00.'],
    [review.start, review.end, 'Review. Illustrative example. Exemplo, Lda. NIF 999 999 990. VAT estimate €23.00. Total €123.00.'],
    [q4.start, q4.end, 'Filing deadline: 22 February 2027. An estimate. This figure ignores VAT on sales.'],
    [q1.start, q1.end, 'Filing deadline: 20 May 2026. An estimate. Deductible VAT €23.00.'],
    [pack.start, pack.end, 'Send to the accountant.'],
  ]);
  return { pt, en };
}
