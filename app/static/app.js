document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => document.getElementById(b.dataset.open).showModal()));
  document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => document.getElementById(b.dataset.close).close()));
  const contactForm = document.getElementById('contact-form');
  const contactDialog = document.getElementById('contact-dialog');
  const resetContactForm = () => {
    if (!contactForm) return;
    contactForm.action = '/contacts';
    contactForm.reset();
    contactForm.elements.active.checked = true;
    contactForm.querySelectorAll('button[type="submit"], button:not([type])').forEach(button => {
      button.disabled = false;
      if (button.dataset.submitLabel) button.textContent = button.dataset.submitLabel;
    });
    const title = document.getElementById('contact-title');
    if (title) title.textContent = 'Nuevo contacto';
  };
  document.querySelectorAll('[data-new-contact]').forEach(button => button.addEventListener('click', () => {
    resetContactForm();
    contactDialog?.showModal();
  }));
  document.querySelectorAll('[data-import-file]').forEach(button => button.addEventListener('click', () => {
    const form = button.closest('form');
    form?.querySelector('.import-file')?.click();
  }));
  document.querySelectorAll('.import-file').forEach(input => input.addEventListener('change', () => {
    if (input.files.length > 0) input.closest('form')?.submit();
  }));
  contactForm?.addEventListener('submit', () => {
    contactForm.querySelectorAll('button[type="submit"], button:not([type])').forEach(button => {
      button.disabled = true;
      if (button.dataset.submitLabel) button.textContent = 'Guardando…';
    });
  });
  document.querySelectorAll('.preview-shell img').forEach(img => {
    const shell = img.closest('.preview-shell');
    const done = () => shell?.classList.remove('is-loading');
    const fail = () => { shell?.classList.remove('is-loading'); shell?.classList.add('has-error'); const label = shell?.querySelector('.preview-loader strong'); if (label) label.textContent = 'No se pudo cargar'; };
    if (img.complete && img.naturalWidth > 0) done();
    else if (img.complete) fail();
    img.addEventListener('load', done, { once: true });
    img.addEventListener('error', fail, { once: true });
  });
  document.querySelectorAll('.edit-contact').forEach(button => button.addEventListener('click', () => {
    const form = document.getElementById('contact-form');
    form.action = `/contacts/${button.dataset.id}`;
    form.querySelectorAll('button[type="submit"], button:not([type])').forEach(button => {
      button.disabled = false;
      if (button.dataset.submitLabel) button.textContent = button.dataset.submitLabel;
    });
    form.elements.first_name.value = button.dataset.first;
    form.elements.last_name.value = button.dataset.last;
    form.elements.birth_day.value = button.dataset.birthDay;
    form.elements.birth_month.value = button.dataset.birthMonth;
    form.elements.anniversary_date.value = button.dataset.anniversary;
    form.elements.active.checked = button.dataset.active === 'true';
    document.getElementById('contact-title').textContent = 'Editar contacto';
    document.getElementById('contact-dialog').showModal();
  }));
  document.querySelectorAll('.source-button').forEach(button => button.addEventListener('click', async () => {
    const dialog = document.getElementById('source-dialog');
    document.getElementById('source-title').textContent = button.dataset.name.replaceAll('_', ' ');
    document.getElementById('source-code').textContent = 'Cargando…';
    dialog.showModal();
    try { const response = await fetch(button.dataset.url); const data = await response.json(); document.getElementById('source-code').textContent = data.source || data.detail; }
    catch { document.getElementById('source-code').textContent = 'No se pudo cargar la plantilla.'; }
  }));
  const toast = document.querySelector('.toast'); if (toast) setTimeout(() => toast.remove(), 5000);
});
