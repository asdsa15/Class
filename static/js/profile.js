/* 个人中心：查看账号信息、修改姓名、修改密码 */
document.addEventListener('DOMContentLoaded', function () {
  function loadProfile() {
    api('/api/auth/me').then(function (user) {
      document.getElementById('pUsername').textContent = user.username;
      document.getElementById('pRealName').textContent = user.real_name || '未填写';
      document.getElementById('pRole').textContent = user.role_name;
      document.getElementById('pStatus').textContent = user.status_name;
      document.getElementById('pLastLogin').textContent = user.last_login_time
        ? fmtDateTime(user.last_login_time) : '本次为首次登录';
      document.getElementById('pCreateTime').textContent = fmtDateTime(user.create_time);
      document.getElementById('profileRealName').value = user.real_name || '';
    }).catch(function (err) {
      toast(err.message, 'error');
    });
  }

  document.getElementById('nameForm').addEventListener('submit', function (event) {
    event.preventDefault();
    var button = document.getElementById('nameSaveBtn');
    button.disabled = true;
    api('/api/auth/me', {
      method: 'PUT',
      body: { real_name: document.getElementById('profileRealName').value.trim() },
    }).then(function () {
      toast('姓名已更新', 'success');
      loadProfile();
    }).catch(function (err) {
      toast(err.message, 'error');
    }).finally(function () {
      button.disabled = false;
    });
  });

  document.getElementById('passwordForm').addEventListener('submit', function (event) {
    event.preventDefault();
    var errorBox = document.getElementById('passwordError');
    var oldPassword = document.getElementById('oldPassword').value;
    var newPassword = document.getElementById('newPassword').value;
    var confirm = document.getElementById('confirmPassword').value;
    errorBox.style.display = 'none';
    if (newPassword !== confirm) {
      errorBox.textContent = '两次输入的新密码不一致';
      errorBox.style.display = 'block';
      return;
    }
    var button = document.getElementById('passwordSaveBtn');
    button.disabled = true;
    api('/api/auth/password', {
      method: 'POST',
      body: { old_password: oldPassword, new_password: newPassword },
    }).then(function (result) {
      toast(result.message || '密码修改成功', 'success');
      setTimeout(function () { window.location.href = '/login'; }, 1500);
    }).catch(function (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = 'block';
    }).finally(function () {
      button.disabled = false;
    });
  });

  loadProfile();
});
