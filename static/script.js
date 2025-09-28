document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  const username = document.getElementById('username');
  const pwd = document.getElementById('password');
  const alertBox = document.getElementById('alert');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    alertBox.classList.remove('show');

    const payload = {
      username: username.value.trim(),
      password: pwd.value
    };

    try {
      const resp = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (resp.ok) {
        window.location.href = '/dashboard'; // vai para Streamlit
      } else {
        alertBox.textContent = 'Usuário ou senha inválidos.';
        alertBox.classList.add('show');
      }
    } catch (err) {
      alertBox.textContent = 'Erro de rede. Tente novamente.';
      alertBox.classList.add('show');
    }
  });
});
