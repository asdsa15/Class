/* 课程管理页面脚本 */
document.addEventListener('DOMContentLoaded', function () {
  const modal = document.getElementById('courseModal');
  const form = document.getElementById('courseForm');
  let courses = [];

  function openModal(course) {
    document.getElementById('modalTitle').textContent = course ? '编辑课程' : '新建课程';
    document.getElementById('courseId').value = course ? course.id : '';
    document.getElementById('courseName').value = course ? course.course_name : '';
    document.getElementById('className').value = course ? course.class_name : '';
    document.getElementById('classroom').value = course ? course.classroom : '';
    document.getElementById('description').value = course ? course.description : '';
    modal.classList.add('show');
  }

  function closeModal() { modal.classList.remove('show'); }

  async function loadCourses() {
    const keyword = document.getElementById('keyword').value.trim();
    const query = keyword ? '?keyword=' + encodeURIComponent(keyword) : '';
    const body = document.getElementById('courseBody');
    try {
      courses = await api('/api/courses' + query);
      if (!courses.length) {
        body.innerHTML = '<tr><td class="empty" colspan="8">暂无课程，请点击右上角「新建课程」</td></tr>';
        return;
      }
      body.innerHTML = courses.map((course) => `
        <tr>
          <td><strong>${esc(course.course_name)}</strong></td>
          <td>${esc(course.teacher_name) || '--'}</td>
          <td>${esc(course.class_name) || '--'}</td>
          <td>${esc(course.classroom) || '--'}</td>
          <td>${course.session_count}</td>
          <td>${fmtPercent(course.avg_attention)}</td>
          <td>${fmtDateTime(course.create_time)}</td>
          <td>
            <a class="btn btn-sm btn-primary" href="/classroom?course_id=${course.id}">开始课堂</a>
            <button class="btn btn-sm" data-edit="${course.id}">编辑</button>
            <button class="btn btn-sm btn-danger" data-del="${course.id}">删除</button>
          </td>
        </tr>`).join('');
    } catch (err) {
      body.innerHTML = '<tr><td class="empty" colspan="8">加载失败：' + esc(err.message) + '</td></tr>';
    }
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const id = document.getElementById('courseId').value;
    const payload = {
      course_name: document.getElementById('courseName').value.trim(),
      class_name: document.getElementById('className').value.trim(),
      classroom: document.getElementById('classroom').value.trim(),
      description: document.getElementById('description').value.trim(),
    };
    const button = document.getElementById('saveBtn');
    button.disabled = true;
    try {
      if (id) {
        await api('/api/courses/' + id, { method: 'PUT', body: payload });
        toast('课程已更新', 'success');
      } else {
        await api('/api/courses', { method: 'POST', body: payload });
        toast('课程创建成功', 'success');
      }
      closeModal();
      loadCourses();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById('courseBody').addEventListener('click', async function (event) {
    const editId = event.target.dataset ? event.target.dataset.edit : null;
    const delId = event.target.dataset ? event.target.dataset.del : null;
    if (editId) {
      const course = courses.find((item) => String(item.id) === String(editId));
      if (course) openModal(course);
    }
    if (delId) {
      const course = courses.find((item) => String(item.id) === String(delId));
      if (!window.confirm('确定删除课程「' + (course ? course.course_name : '') + '」及其全部课堂记录吗？')) return;
      try {
        await api('/api/courses/' + delId, { method: 'DELETE' });
        toast('课程已删除', 'success');
        loadCourses();
      } catch (err) { toast(err.message, 'error'); }
    }
  });

  document.getElementById('newCourseBtn').addEventListener('click', () => openModal(null));
  document.getElementById('cancelBtn').addEventListener('click', closeModal);
  document.getElementById('searchBtn').addEventListener('click', loadCourses);
  document.getElementById('keyword').addEventListener('keyup', (event) => {
    if (event.key === 'Enter') loadCourses();
  });
  modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });
  loadCourses();
});
