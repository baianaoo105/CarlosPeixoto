(() => {
  const body = document.body;
  const expectedToken = body.dataset.adminSessionToken;
  if (!expectedToken) return;

  const storageKey = 'jcp-admin-tab-session';
  const freshLogin = body.dataset.adminSessionFresh === '1';

  if (freshLogin) {
    sessionStorage.setItem(storageKey, expectedToken);
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete('login');
    window.history.replaceState({}, '', cleanUrl.pathname + cleanUrl.search + cleanUrl.hash);
    return;
  }

  if (sessionStorage.getItem(storageKey) !== expectedToken) {
    sessionStorage.removeItem(storageKey);
    window.location.replace(body.dataset.adminLogoutUrl);
  }
})();
