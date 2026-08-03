const button = document.querySelector('.menu-button');
const menu = document.querySelector('#main-menu');
button?.addEventListener('click', () => {
  const open = button.getAttribute('aria-expanded') === 'true';
  button.setAttribute('aria-expanded', String(!open));
  menu.classList.toggle('open');
});
document.querySelectorAll('[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
  const message = form.dataset.confirmMessage || 'Tem certeza que deseja excluir esta notícia? Os comentários também serão excluídos.';
  if (!window.confirm(message)) event.preventDefault();
}));

const musicForm = document.querySelector('.music-form[data-chunk-upload-url]');
if (musicForm) {
  const audioInput = musicForm.querySelector('input[name="audio"]');
  const sourceInput = musicForm.querySelector('input[name="source_url"]');
  const tokenInput = musicForm.querySelector('input[name="uploaded_audio_token"]');
  const progressBox = musicForm.querySelector('.music-upload-progress');
  const progressBar = progressBox?.querySelector('span');
  const progressText = progressBox?.querySelector('p');
  let uploadPrepared = false;
  let uploading = false;

  const newUploadToken = () => {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    const bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hexadecimal = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    return `${hexadecimal.slice(0, 8)}-${hexadecimal.slice(8, 12)}-${hexadecimal.slice(12, 16)}-${hexadecimal.slice(16, 20)}-${hexadecimal.slice(20)}`;
  };

  audioInput?.addEventListener('change', () => {
    uploadPrepared = false;
    if (tokenInput) tokenInput.value = '';
    if (progressBox) progressBox.hidden = true;
  });

  musicForm.addEventListener('submit', async (event) => {
    const file = audioInput?.files?.[0];
    if (uploadPrepared || !file) return;
    if (uploading) {
      event.preventDefault();
      return;
    }
    event.preventDefault();

    if (!musicForm.reportValidity()) return;
    if (sourceInput?.value.trim()) {
      window.alert('Escolha somente uma fonte: apague o link ou remova o arquivo de áudio.');
      return;
    }

    const maximumSize = Number(musicForm.dataset.maxAudioSize || 0);
    const chunkSize = Number(musicForm.dataset.chunkSize || 0);
    if (!maximumSize || !chunkSize) {
      window.alert('Não foi possível preparar o envio do áudio. Atualize a página e tente novamente.');
      return;
    }
    if (!file.size) {
      window.alert('O arquivo de áudio está vazio.');
      return;
    }
    if (file.size > maximumSize) {
      window.alert('O áudio ultrapassa o limite de 50 MB.');
      return;
    }

    uploading = true;
    const submitButton = musicForm.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    if (progressBox) progressBox.hidden = false;

    try {
      const token = newUploadToken();
      const totalChunks = Math.ceil(file.size / chunkSize);
      for (let index = 0; index < totalChunks; index += 1) {
        const start = index * chunkSize;
        const chunk = file.slice(start, Math.min(file.size, start + chunkSize), file.type);
        const formData = new FormData();
        formData.append('upload_token', token);
        formData.append('chunk_index', String(index));
        formData.append('total_chunks', String(totalChunks));
        formData.append('filename', file.name);
        formData.append('mimetype', file.type);
        formData.append('chunk', chunk, file.name);

        const response = await window.fetch(musicForm.dataset.chunkUploadUrl, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
        });
        let payload = null;
        try {
          payload = await response.json();
        } catch (_error) {
          throw new Error('A sessão do painel expirou ou o servidor não respondeu corretamente.');
        }
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || 'Uma parte do áudio não pôde ser enviada.');
        }

        const percent = Math.round(((index + 1) / totalChunks) * 100);
        if (progressBar) progressBar.style.width = `${percent}%`;
        if (progressText) progressText.textContent = `Enviando áudio: ${percent}% (${index + 1} de ${totalChunks} partes)`;
      }

      if (tokenInput) tokenInput.value = token;
      if (audioInput) audioInput.value = '';
      uploadPrepared = true;
      if (progressText) progressText.textContent = 'Áudio enviado. Salvando a música…';
      HTMLFormElement.prototype.submit.call(musicForm);
    } catch (error) {
      uploading = false;
      if (submitButton) submitButton.disabled = false;
      if (progressText) progressText.textContent = 'O envio foi interrompido.';
      window.alert(error instanceof Error ? error.message : 'Não foi possível enviar o áudio.');
    }
  });
}
