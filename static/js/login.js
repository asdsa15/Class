/* 登录页脚本 */
document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('loginForm');
  const errorBox = document.getElementById('loginError');
  const button = document.getElementById('loginBtn');
  const rememberBox = document.getElementById('rememberMe');
  const usernameInput = document.getElementById('username');
  const REMEMBER_KEY = 'classroom_remember_username';

  /* 恢复上次记住的账号（只保存账号，不保存明文密码） */
  try {
    const saved = localStorage.getItem(REMEMBER_KEY);
    if (saved) {
      usernameInput.value = saved;
      rememberBox.checked = true;
      document.getElementById('password').focus();
    }
  } catch (err) { /* 浏览器禁用本地存储时忽略 */ }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    errorBox.style.display = 'none';
    button.disabled = true;
    button.textContent = '登录中…';
    const username = usernameInput.value.trim();
    const remember = rememberBox.checked;
    try {
      await api('/api/auth/login', {
        method: 'POST',
        body: { username: username, password: document.getElementById('password').value, remember_me: remember },
      });
      try {
        if (remember) {
          localStorage.setItem(REMEMBER_KEY, username);
        } else {
          localStorage.removeItem(REMEMBER_KEY);
        }
      } catch (err) { /* 忽略本地存储异常 */ }
      window.location.href = '/dashboard';
    } catch (err) {
      errorBox.textContent = err.message || '登录失败';
      errorBox.style.display = 'block';
      button.disabled = false;
      button.textContent = '登 录';
    }
  });
});
