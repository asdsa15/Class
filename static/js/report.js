/* 课堂分析报告页面脚本 */
document.addEventListener('DOMContentLoaded', async function () {
  const sessionId = window.location.pathname.split('/').pop();
  if (!sessionId) return;

  try {
    const report = await api('/api/reports/' + sessionId);
    const statistics = await api('/api/reports/' + sessionId + '/statistics');

    document.getElementById('reportTitle').textContent = report.course_name + ' · 课堂分析报告';
    document.getElementById('rCourse').textContent = report.course_name || '--';
    document.getElementById('rClass').textContent = report.class_name || '--';
    document.getElementById('rTeacher').textContent = report.teacher_name || '--';
    document.getElementById('rRoom').textContent = report.classroom || '--';
    document.getElementById('rTime').textContent =
      fmtDateTime(report.start_time) + (report.end_time ? ' ~ ' + fmtTime(report.end_time) : '（进行中）');
    document.getElementById('rDuration').textContent = fmtDuration(report.duration_minutes);
    document.getElementById('rAvg').innerHTML = fmtPercent(report.avg_attention).replace('%', '<small>%</small>');
    document.getElementById('rMax').innerHTML = fmtPercent(report.max_attention).replace('%', '<small>%</small>');
    document.getElementById('rMin').innerHTML = fmtPercent(report.min_attention).replace('%', '<small>%</small>');
    document.getElementById('rCount').innerHTML =
      report.record_count + ' <small>次 / ' + report.student_count + ' 人</small>';
    document.getElementById('rLevel').textContent = report.level || '无有效数据';

    Chart.line(document.getElementById('trendChart'), {
      labels: (report.attention_series || []).map((item) => item.time),
      values: (report.attention_series || []).map((item) => item.score),
      height: 260,
      emptyText: '本节课堂暂无专注度采样数据',
    });

    const behaviors = statistics.behavior_series || [];
    Chart.bar(document.getElementById('behaviorChart'), {
      labels: behaviors.map((item) => item.name_cn),
      values: behaviors.map((item) => item.count),
      colors: behaviors.map((item) => behaviorColor(item.key)),
      height: 260,
      emptyText: '本节课堂暂无行为统计数据',
    });

    const pieItems = behaviors.filter((item) => item.count > 0).map((item) => ({
      name: item.name_cn, value: item.count, color: behaviorColor(item.key), key: item.key,
    }));
    Chart.pie(document.getElementById('pieChart'), { items: pieItems, height: 250, emptyText: '暂无行为数据' });
    const total = pieItems.reduce((sum, item) => sum + item.value, 0);
    document.getElementById('pieLegend').innerHTML = pieItems.map((item) =>
      '<span><i style="background:' + item.color + '"></i>' + esc(item.name) + ' ' + item.value +
      '（' + (total ? (item.value / total * 100).toFixed(1) : '0.0') + '%）</span>'
    ).join('') || '<span class="hint">暂无行为数据</span>';

    Chart.bar(document.getElementById('distChart'), {
      labels: (statistics.distribution || []).map((item) => item.label),
      values: (statistics.distribution || []).map((item) => item.count),
      color: '#00b3a4',
      height: 250,
      emptyText: '暂无专注度分布数据',
    });

    document.getElementById('behaviorBody').innerHTML = behaviors.map((item) => `
      <tr>
        <td><strong>${esc(item.name_cn)}</strong></td>
        <td>${esc(item.name_en)}</td>
        <td>${item.count}</td>
        <td>${Number(item.ratio).toFixed(2)}%</td>
        <td>${(item.avg_confidence * 100).toFixed(2)}%</td>
        <td>${item.weight}</td>
        <td>${item.focused
          ? '<span style="color:#2f855a">专注</span>'
          : '<span style="color:#c2760b">非专注</span>'}</td>
      </tr>`).join('');

    document.getElementById('summaryList').innerHTML =
      (report.summary || ['暂无总结']).map((line) => '<li>' + esc(line) + '</li>').join('');
  } catch (err) {
    toast(err.message, 'error');
    document.getElementById('summaryList').innerHTML = '<li>报告加载失败：' + esc(err.message) + '</li>';
  }
});
