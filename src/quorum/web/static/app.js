// Progressive enhancement only: every feature also works without this file.

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-copy]');
  if (!button) return;
  const field = document.getElementById(button.dataset.copy);
  if (!field) return;
  navigator.clipboard.writeText(field.value).then(
    () => {
      button.textContent = 'Copied';
      setTimeout(() => { button.textContent = 'Copy'; }, 2000);
    },
    () => field.select(),
  );
});

document.addEventListener('input', (event) => {
  const field = event.target;
  if (!(field instanceof HTMLTextAreaElement) || !field.dataset.counter) return;
  const counter = document.getElementById(field.dataset.counter);
  if (!counter) return;
  const left = field.maxLength - field.value.length;
  counter.textContent = field.value.length === 0 ? `Up to ${field.maxLength} characters.` : `${left} characters left.`;
});
