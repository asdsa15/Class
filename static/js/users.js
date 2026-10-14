/* 用户管理页面（仅管理员）：列表、创建、修改、禁用/启用、重置密码、删除 */
document.addEventListener('DOMContentLoaded', function () {
  var users = [];
  var userModal = document.getElementById('userModal');
  var resetModal = document.getElementById('resetModal');
  var userForm = document.getElementById('userForm');
  var resetForm = document.getElementById('resetForm');

  function showError(message) {
    var box = document.getElementById('userFormError');
    box.textContent = message;
    box.style.display = message ? 'block' : 'none';
  }

  function loadUsers() {
    var body = document.getElementById('userBody');
    var keyword = document.getElementById('userKeyword').value.trim().toLowerCase();
    api('/api/auth/users').then(function (data) {
      users = data;
      var rows = data.filter(function (item) {
        if (!keyword) return true;
        return (item.username + ' ' + (item.real_name || '')).toLowerCase().indexOf(keyword) >= 0;
      });
      if (!rows.length) {
        body.innerHTML = '<tr><td class="empty" colspan="9">没有符合条件的用户</td></tr>';
        return;
      }
      body.innerHTML = rows.map(function (item) {
        var statusText = item.status === 1
          ? '<span style="color:#2f9e44">正常</span>'
          : '<span style="color:#d92d20">已禁用</span>';
        var toggleText = item.status === 1 ? '禁用' : '启用';
        return '<tr>' +
          '<td>' + item.id + '</td>' +
          '<td class="strong">' + esc(item.username) + '</td>' +
          '<td>' + (esc(item.real_name) || '--') + '</td>' +
          '<td>' + esc(item.role_name) + '</td>' +
          '<td>' + statusText + '</td>' +
          '<td class="num">' + item.course_count + '</td>' +
          '<td>' + (item.last_login_time ? fmtDateTime(item.last_login_time) : '从未登录') + '</td>' +
          '<td>' + fmtDateTime(item.create_time) + '</td>' +
          '<td>' +
          '<button class="btn btn-sm" data-edit="' + item.id + '">修改</button> ' +
          '<button class="btn btn-sm" data-reset="' + item.id + '">重置密码</button> ' +
          '<button class="btn btn-sm" data-toggle="' + item.id + '">' + toggleText + '</button> ' +
          '<button class="btn btn-sm btn-danger" data-del="' + item.id + '">删除</button>' +
          '</td></tr>';
      }).join('');
    }).catch(function (err) {
      body.innerHTML = '<tr><td class="empty" colspan="9">加载失败：' + esc(err.message) + '</td></tr>';
    });
  }

  function openCreate() {
    document.getElementById('userModalTitle').textContent = '创建用户';
    document.getElementById('editUserId').value = '';
    document.getElementById('newUsername').value = '';
    document.getElementById('newUsername').disabled = false;
    document.getElementById('newRealName').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    document.getElementById('newRole').value = 'teacher';
    document.getElementById('passwordRow').style.display = '';
    document.getElementById('confirmPasswordRow').style.display = '';
    document.getElementById('statusRow').style.display = 'none';
    showError('');
    userModal.classList.add('show');
  }

  function openEdit(user) {
    document.getElementById('userModalTitle').textContent = '修改用户：' + user.username;
    document.getElementById('editUserId').value = user.id;
    document.getElementById('newUsername').value = user.username;
    document.getElementById('newUsername').disabled = true;
    document.getElementById('newRealName').value = user.real_name || '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    document.getElementById('newRole').value = user.role;
    document.getElementById('passwordRow').style.display = 'none';
    document.getElementById('confirmPasswordRow').style.display = 'none';
    document.getElementById('statusRow').style.display = '';
    document.getElementById('newStatus').value = String(user.status);
    showError('');
    userModal.classList.add('show');
  }

  userForm.addEventListener('submit', function (event) {
    event.preventDefault();
    var id = document.getElementById('editUserId').value;
    var realName = document.getElementById('newRealName').value.trim();
    var role = document.getElementById('newRole').value;
    var button = document.getElementById('userSaveBtn');
    button.disabled = true;
    showError('');

    var request;
    if (id) {
      request = api('/api/auth/users/' + id, {
        method: 'PUT',
        body: { real_name: realName, role: role, status: Number(document.getElementById('newStatus').value) },
      }).then(function () { toast('用户信息已更新', 'success'); });
    } else {
      var password = document.getElementById('newPassword').value;
      var confirm = document.getElementById('confirmPassword').value;
      if (password !== confirm) {
        showError('两次输入的密码不一致');
        button.disabled = false;
        return;
      }
      request = api('/api/auth/users', {
        method: 'POST',
        body: {
          username: document.getElementById('newUsername').value.trim(),
          real_name: realName,
          password: password,
          role: role,
        },
      }).then(function () { toast('用户创建成功', 'success'); });
    }

    request.then(function () {
      userModal.classList.remove('show');
      loadUsers();
    }).catch(function (err) {
      showError(err.message);
    }).finally(function () {
      button.disabled = false;
    });
  });

  resetForm.addEventListener('submit', function (event) {
    event.preventDefault();
    var id = document.getElementById('resetUserId').value;
    var password = document.getElementById('resetPassword').value;
    var button = document.getElementById('resetSaveBtn');
    button.disabled = true;
    api('/api/auth/users/' + id + '/reset-password', {
      method: 'POST',
      body: { new_password: password },
    }).then(function (result) {
      toast(result.message || '密码已重置', 'success');
      resetModal.classList.remove('show');
    }).catch(function (err) {
      toast(err.message, 'error');
    }).finally(function () {
      button.disabled = false;
    });
  });

  document.getElementById('userBody').addEventListener('click', function (event) {
    var target = event.target;
    if (!target.dataset) return;
    var id = target.dataset.edit || target.dataset.reset || target.dataset.toggle || target.dataset.del;
    if (!id) return;
    var user = users.filter(function (item) { return String(item.id) === String(id); })[0];
    if (!user) return;

    if (target.dataset.edit) {
      openEdit(user);
      return;
    }
    if (target.dataset.reset) {
      document.getElementById('resetUserId').value = user.id;
      document.getElementById('resetPassword').value = '';
      document.getElementById('resetHint').textContent =
        '为账号「' + user.username + '」（' + (user.real_name || '未填写姓名') + '）设置新密码。';
      resetModal.classList.add('show');
      return;
    }
    if (target.dataset.toggle) {
      var nextStatus = user.status === 1 ? 0 : 1;
      var action = nextStatus === 1 ? '启用' : '禁用';
      if (!window.confirm('确定' + action + '账号「' + user.username + '」吗？')) return;
      api('/api/auth/users/' + user.id, { method: 'PUT', body: { status: nextStatus } })
        .then(function () { toast('账号已' + action, 'success'); loadUsers(); })
        .catch(function (err) { toast(err.message, 'error'); });
      return;
    }
    if (target.dataset.del) {
      if (!window.confirm('确定删除账号「' + user.username + '」吗？该操作不可恢复。')) return;
      api('/api/auth/users/' + user.id, { method: 'DELETE' })
        .then(function () { toast('用户已删除', 'success'); loadUsers(); })
        .catch(function (err) { toast(err.message, 'error'); });
    }
  });

  document.getElementById('newUserBtn').addEventListener('click', openCreate);
  document.getElementById('userCancelBtn').addEventListener('click', function () {
    userModal.classList.remove('show');
  });
  document.getElementById('resetCancelBtn').addEventListener('click', function () {
    resetModal.classList.remove('show');
  });
  document.getElementById('userSearchBtn').addEventListener('click', loadUsers);
  document.getElementById('userKeyword').addEventListener('keyup', function (event) {
    if (event.key === 'Enter') loadUsers();
  });
  loadUsers();
});
