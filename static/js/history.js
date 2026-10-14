/* 历史课堂页面脚本 */
document.addEventListener('DOMContentLoaded', async function () {
  const courseFilter = document.getElementById('courseFilter');
  const compareCourse = document.getElementById('compareCourse');
  let sessions = [];

  try {
    const courses = await api('/api/courses');
    const options = courses.map((course) => `<option value="${course.id}">${esc(course.course_name)}</option>`).join('');
    courseFilter.innerHTML = '<option value="">全部课程</option>' + options;
    compareCourse.innerHTML = options || '<option value="">暂无课程</option>';
  } catch (err) {
    toast(err.message, 'error');
  }

  async function loadSessions() {
    const body = document.getElementById('historyBody');
    const courseId = courseFilter.value;
    try {
      const rows = await api('/api/classrooms' + (courseId ? '?course_id=' + courseId : ''));
      const startDate = document.getElementById('startDate').value;
      const endDate = document.getElementById('endDate').value;
      sessions = rows.filter((item) => {
        if (startDate && item.date < startDate) return false;
        if (endDate && item.date > endDate) return false;
        return true;
      });
      if (!sessions.length) {
        body.innerHTML = '<tr><td class="empty" colspan="10">暂无符合条件的课堂记录</td></tr>';
        document.getElementById('summaryHint').textContent = '';
        return;
      }
      const withData = sessions.filter((item) => item.avg_attention !== null);
      const average = withData.length
        ? (withData.reduce((sum, item) => sum + item.avg_attention, 0) / withData.length).toFixed(1) + '%'
        : '--';
      document.getElementById('summaryHint').textContent =
        '共 ' + sessions.length + ' 次课堂，平均专注度 ' + average;
      body.innerHTML = sessions.map((item) => `
        <tr>
          <td><strong>${esc(item.course_name)}</strong></td>
          <td>${esc(item.class_name) || '--'}</td>
          <td>${esc(item.date)}</td>
          <td>${esc(item.time_range) || '--'}</td>
          <td>${fmtDuration(item.duration_minutes)}</td>
          <td><strong>${fmtPercent(item.avg_attention)}</strong></td>
          <td>${fmtPercent(item.max_attention)} / ${fmtPercent(item.min_attention)}</td>
          <td>${item.record_count}</td>
          <td>${statusBadge(item.status)}</td>
          <td>
            <a class="btn btn-sm btn-primary" href="/report/${item.id}">查看报告</a>
            ${item.status === 'running' ? '<a class="btn btn-sm" href="/classroom?session_id=' + item.id + '">继续检测</a>' : ''}
            <button class="btn btn-sm btn-danger" data-del="${item.id}">删除</button>
          </td>
        </tr>`).join('');
    } catch (err) {
      body.innerHTML = '<tr><td class="empty" colspan="10">加载失败：' + esc(err.message) + '</td></tr>';
    }
  }

  document.getElementById('historyBody').addEventListener('click', async function (event) {
    const id = event.target.dataset ? event.target.dataset.del : null;
    if (!id) return;
    if (!window.confirm('确定删除该课堂记录及其行为、专注度数据吗？')) return;
    try {
      await api('/api/classrooms/' + id, { method: 'DELETE' });
      toast('课堂记录已删除', 'success');
      loadSessions();
    } catch (err) { toast(err.message, 'error'); }
  });

  document.getElementById('filterBtn').addEventListener('click', loadSessions);
  courseFilter.addEventListener('change', loadSessions);
  Chart.line(document.getElementById('compareChart'), {
    labels: [],
    values: [],
    height: 250,
    emptyText: '选择课程后点击「生成对比图」查看历次课堂的专注度变化',
  });
  document.getElementById('compareBtn').addEventListener('click', async function () {
    const courseId = compareCourse.value;
    const hint = document.getElementById('compareHint');
    if (!courseId) { toast('请先选择课程', 'error'); return; }
    try {
      const data = await api('/api/reports/courses/' + courseId + '/compare');
      Chart.line(document.getElementById('compareChart'), {
        labels: data.labels,
        values: data.values,
        height: 250,
        color: '#00b3a4',
        emptyText: '该课程暂无已结束课堂的专注度数据',
      });
      hint.textContent = data.sessions.length
        ? '课程「' + data.course_name + '」共 ' + data.sessions.length + ' 次课堂，平均专注度 ' + data.avg_attention + '%'
        : '该课程暂无已结束课堂的专注度数据';
    } catch (err) { toast(err.message, 'error'); }
  });
  loadSessions();
});
