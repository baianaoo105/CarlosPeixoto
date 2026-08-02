const button = document.querySelector('.menu-button');
const menu = document.querySelector('#main-menu');
button?.addEventListener('click', () => {
  const open = button.getAttribute('aria-expanded') === 'true';
  button.setAttribute('aria-expanded', String(!open));
  menu.classList.toggle('open');
});
document.querySelectorAll('[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
  if (!window.confirm('Tem certeza que deseja excluir esta notícia? Os comentários também serão excluídos.')) event.preventDefault();
}));

