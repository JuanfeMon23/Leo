/** Nombre de archivo seguro: sin separadores de ruta ni caracteres de control. */
export function safeDownloadName(name: string): string {
  const cleaned = name
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[\\/]+/g, '-')
    .replace(/^[-.\s]+/, '')
    .trim()
  return cleaned || 'descarga'
}

/** Guarda un `Blob` como archivo en el navegador (enlace temporal con `download`). */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = safeDownloadName(filename)
  link.rel = 'noopener'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
